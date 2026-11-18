import random
from collections import Counter

OPENERS = ["hi", "hey everyone", "hello!", "hi all", "hey"]

GENERAL = [
    "so we need to pick a decision maker right?",
    "any thoughts on who should do it?",
    "i think we should pick someone who explains their reasoning clearly",
    "what do you think matters most for this role",
    "i'm fine with whoever, i just want it to be fair",
    "maybe whoever has the best reasoning?",
    "we only have a minute so lets decide quickly",
    "does anyone have a strong preference?",
]

SUGGEST = [
    "i think {other} would be a good choice",
    "{other} seems thoughtful, i'd go with them",
    "how about {other}?",
    "{other} has made good points so far",
]

REACT_TO_NAME = [
    "{named}? why them?",
    "hmm, what makes you pick {named}?",
    "i could see {named} working",
]

AGREE = ["yeah that makes sense", "agreed", "good point", "fair enough", "ok i can go with that"]


class ScriptedProvider:
    """No API key needed. Behaviour is simple on purpose and easy to explain."""

    def __init__(self):
        self.used: set[str] = set()
        self.favorite: str | None = None

    # ---- helpers ----

    def _pick(self, pool: list[str]) -> str:
        fresh = [t for t in pool if t not in self.used]
        if not fresh:  # everything used once, allow repeats again
            self.used.difference_update(pool)
            fresh = pool
        choice = random.choice(fresh)
        self.used.add(choice)
        return choice

    @staticmethod
    def _activity(ctx: dict) -> Counter:
        me = ctx["you"]
        return Counter(m["from"] for m in ctx["messages"] if m["from"] != me)

    def _choose_favorite(self, ctx: dict) -> str:
        if self.favorite:
            return self.favorite
        others = [p for p in ctx["players"] if p != ctx["you"]]
        activity = self._activity(ctx)
        if activity:
            top = max(activity.values())
            others = [p for p in others if activity.get(p, 0) == top] or others
        self.favorite = random.choice(others)
        return self.favorite

    # ---- interface ----

    async def generate_message(self, ctx: dict) -> str | None:
        me = ctx["you"]
        messages = ctx["messages"]
        mine = [m for m in messages if m["from"] == me]

        if random.random() < 0.25:
            return None  # sometimes just read and stay quiet

        if not mine:
            return self._pick(OPENERS) if random.random() < 0.6 else self._pick(GENERAL)

        last = messages[-1] if messages else None
        if last and last["from"] != me:
            named = next(
                (p for p in ctx["players"] if p != me and p in last["text"]), None
            )
            if named and random.random() < 0.6:
                return self._pick(REACT_TO_NAME).format(named=named)
            if random.random() < 0.3:
                return self._pick(AGREE)

        if random.random() < 0.5:
            return self._pick(SUGGEST).format(other=self._choose_favorite(ctx))
        return self._pick(GENERAL)

    async def decide_vote(self, ctx: dict) -> str:
        if self.favorite:
            return self.favorite
        others = [p for p in ctx["players"] if p != ctx["you"]]
        activity = self._activity(ctx)
        if activity:
            return max(others, key=lambda p: (activity.get(p, 0), random.random()))
        return random.choice(others)