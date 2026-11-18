# AI Usage Log

## Tools and models

| Purpose | Tool | Model |
|---|---|---|
| Planning, code generation, debugging help | claude.ai chat interface (no coding agent, no IDE integration) | Claude Sonnet 5.5 |
| AI participants at runtime (the "AI" players in the experiment) | Google Gemini API via its OpenAI-compatible endpoint | `gemini-flash-lite-latest` |
| Fallback AI participants (no API key) | Scripted provider | none |

Time spent: **3** 


## Phase 1: Understanding the task and planning

### Reading the task

**Prompt 1** *(task file attached)*

> I have got a take-home assessment from the Max Planck Institute for Human Development, the task
> is attached. Before I write any code, can you read it carefully and walk me through whats
> really being asked? I would like to know which parts are fixed, which are deliberately left to my
> judgment. One more thing that i noticed it mentions both 2 and 4 hours.
> Then tell me what you would do first, and why.

### Planning

**Prompt 2**

> I have read the requirements and I am ready to start. Can you lay out a step by step plan that
> fits the time limit and explain the reasoning behind the order? I would like
> Docker, WebSockets, etc to be tested early. 

### Design prompt

**Prompt 3**

> Could you write me a prompt I can use to get a one-page design before any code exists,
> it should specially contain my decisions on the open questions.
> Once I havve reviewed the design, we will start with the smallest piece of code that proves the stack works.

### Scope and time decisions

**Prompt 4**

> If I use an LLM for the AI players how long would that add and can I still
> finish in time? If it does not fit how would I explain that trade off in the interview?
>
> Correction on scope: 2 hours is the expectation and 4 hours is the hard maximum so I have
> more room than I assumed. Can you update the plan with that in mind?

**Decision:** treat 2 hours as the target and 4 hours as the ceiling. Build a scripted agent
first, behind a provider interface, and add an LLM provider only once the base flow works.

---

## Phase 2: Step-by-step build

### Step 1: Config file and validation

**Prompt 5 **

> Lets build this one small step at a time. starting with the config file. For each step show
> me the code, tell me what to install first and how to verify it, so any problem gets fixed
> before we move on.
> I'm on Windows with Python 3.13.7


### Step 2: Backend and MongoDB in Docker

**Prompt 6 **

> Passed. next. *(with the logs pasted)* are these logs normal?

**Outcome:** FastAPI and MongoDB running in Compose; the config switch changes the health output.

### Step 3: React frontend, proxy and WebSocket test

**Prompt 7**

> Passed. next. Now add the react frontend and include a quick
> websocket test.

**Outcome:** the full chain (browser, React, proxy, backend, MongoDB, WebSocket) is verified
while the app is still trivial.

### Step 4: Waiting room and sessions

**Prompt 8**

> Next step (waiting room). A refresh should restore the
> same seat.
>
> *(later)* The page is blank after I restarted the backend. Do I need to rebuild, or just
> refresh?

**Decision:** participant type (`human`/`ai`) is stored only in MongoDB and never appears in any payload.

### Step 5: State machine with timers

**Prompt 9**
> Done. next step

> *[pasted the page output after the first full run, showing the Results state]*



### Step 6: Real-time chat

**Prompt 10**
> next step

> *[pasted the chat output from two tabs]*


### Step 7: Voting, tie-breaking, results

**Prompt 11**

> Next, voting. Nobody should see who voted for whom. Also apply tie-breaking rules.

### Step 8: AI agents behind an interface

**Prompt 12**

> Now add the AI participants behind a provider interface starting with a simple scripted one
> so I can test the whole flow. Make it human like. Take some pauses. make some spelling mistakes, etc.

---

## Phase 3: Replacing the scripted AI

### Step 9: LLM-powered agents

**Prompt 13**

> The whole flow works but the scripted AI players are obvious. they say things unrelated to
> the conversation which breaks the blind condition. Lets replace them with an LLM. Replies should be short and casual 
> and if the API fails the session should still complete.

**Key decision:** because of the provider interface, only `agents/llm.py` changed. The session code stayed the same.

### Choosing a free provider

**Prompt 14**

> Is there a free LLM API that needs no credit card? Just the options and trade-offs for now,
> no code yet.
>
> Lets use Gemini. Help me to get an API key and test it before we change any code.
>
> The key works with `gemini-flash-lite-latest`. Please give me all the remaining changes for
> Gemini in one message, plus the final README and a pre-submission checklist, since I'm
> running low on my usage limit again.

**Decisions:**
- Gemini's free tier has tight daily limits, so I use a Flash-Lite model and slower reply delays.
- Provider, model, base URL and key variable are set in `config.yml`, so switching providers needs no code change.
- Failed messages are skipped, failed votes fall back to a scripted vote, and with no key the app uses the scripted provider.


---

## Reflection

- **What worked:** one step at a time, with a verification step after each. Problems were always
  isolated to the latest step. Putting Docker and the WebSocket proxy first removed the biggest
  infrastructure risks early.

- **A real course correction:** the scripted AI passed technical tests but failed the real test
  (a human could tell it wasn't following the conversation). Testing it as a participant, not only
  as a developer, led to the LLM provider.
