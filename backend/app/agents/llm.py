import asyncio
import logging
import os
import re

from openai import AsyncOpenAI

from .scripted import ScriptedProvider

log = logging.getLogger("agents.llm")

SYSTEM_PROMPT = """You are {you}, a participant in a short online group discussion \
with two other participants ({others}). Together you must choose which of the three \
of you should be the "Decision Maker" for a later task. Everyone votes at the end of \
each round, and you may vote for yourself.

How to write:
- You are chatting in a quick text chat. Write like a normal person in a hurry: \
short, casual, mostly lowercase, at most one sentence, usually under 15 words.
- No lists, no markdown, no emojis, no quotation marks, no signature.
- React to what was actually said. Refer to people by their label (e.g. "{example}").
- Share an opinion, ask a short question, agree or disagree. Do not repeat yourself.
- Form your own view about who would make a good Decision Maker, based on how the \
others argue and behave, and be willing to change your mind.
- Do not volunteer anything about what you are. If someone asks about it, deflect \
lightly in one short line and steer back to the task.
- If you have nothing useful to add right now, or you spoke last, reply exactly: [silent]

Output only the chat message itself."""

DISCLOSURE = re.compile(
    r"as an ai|language model|i'?m an ai|i am an ai|artificial intelligence|i'?m a bot|i am a bot",
    re.I,
)


def _transcript(ctx: dict) -> str:
    lines, current_round = [], None
    for m in ctx["messages"]:
        if m.get("round") != current_round:
            current_round = m.get("round")
            lines.append(f"--- round {current_round} ---")
        who = f"{m['from']} (you)" if m["from"] == ctx["you"] else m["from"]
        lines.append(f"{who}: {m['text']}")
    return "\n".join(lines) if lines else "(no messages yet)"


class LLMProvider:
    def __init__(self, config: dict):
        ai = config["ai"]
        self.model = ai["model"]
        self.timeout = ai.get("timeout_seconds", 10)
        self.client = AsyncOpenAI(
            base_url=ai["base_url"],
            api_key=os.environ[ai.get("api_key_env", "GEMINI_API_KEY")],
        )
        self.fallback = ScriptedProvider()  # used for votes only, if the API fails

    def _system(self, ctx: dict) -> str:
        others = [p for p in ctx["players"] if p != ctx["you"]]
        return SYSTEM_PROMPT.format(
            you=ctx["you"], others=" and ".join(others), example=others[0]
        )

    async def _ask(self, ctx: dict, instruction: str, max_tokens: int) -> str:
        content = (
            f"Chat so far (round {ctx['round']}):\n{_transcript(ctx)}\n\n{instruction}"
        )
        resp = await asyncio.wait_for(
            self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0.9,
                messages=[
                    {"role": "system", "content": self._system(ctx)},
                    {"role": "user", "content": content},
                ],
            ),
            timeout=self.timeout,
        )
        return (resp.choices[0].message.content or "").strip()

    async def generate_message(self, ctx: dict) -> str | None:
        messages = ctx["messages"]
        if messages and messages[-1]["from"] == ctx["you"]:
            return None  # never speak twice in a row
        try:
            text = await self._ask(ctx, "Write your next chat message.", max_tokens=150)
        except Exception as e:
            log.warning("LLM message call failed (%s), staying silent", type(e).__name__)
            return None

        text = re.sub(rf"^{re.escape(ctx['you'])}\s*:\s*", "", text).strip().strip('"')
        if not text or "[silent]" in text.lower() or DISCLOSURE.search(text):
            return None
        return text[:250]

    async def decide_vote(self, ctx: dict) -> str:
        hint = ""
        if ctx.get("round1_tally"):
            hint = f" (Round 1 vote counts were: {ctx['round1_tally']}.)"
        try:
            answer = await self._ask(
                ctx,
                "Time to vote for the Decision Maker." + hint
                + " Reply with exactly one label from: "
                + ", ".join(ctx["players"]) + ".",
                max_tokens=50,
            )
            for label in ctx["players"]:
                if label.lower() in answer.lower():
                    return label
        except Exception as e:
            log.warning("LLM vote call failed (%s), using fallback vote", type(e).__name__)
        return await self.fallback.decide_vote(ctx)