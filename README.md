# Group Decision Experiment (Human-AI, 3 participants)

A real-time web app simulating a 3-participant group decision experiment.
Participants discuss for 2 rounds, vote for a "Decision Maker" after each,
and see the final result. Participants cannot tell who is human or AI.

## Run

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (free key from https://aistudio.google.com/apikey).
   Without a key, AI agents fall back to a simple scripted provider.
2. `docker compose up --build`
3. Open http://localhost:5173. Use one browser tab per human player
   (tabs have separate identities).

## Switch conditions (`config.yml`)

| Condition | `session.participants` | Tabs needed |
|---|---|---|
| 3 humans | `[human, human, human]` | 3 |
| 2 humans + 1 AI | `[human, human, ai]` | 2 |
| 1 human + 2 AIs | `[human, ai, ai]` | 1 |

After editing: `docker compose restart backend`.
Other settings: round count and durations, `results.round1_feedback`
(`none`/`tally`), `results.tie_break` (`random`/`round1`), AI provider,
model, base URL and reply delays.

## Architecture

- **Backend:** FastAPI + WebSocket (`/ws/session`), MongoDB for storage.
- **Frontend:** React (Vite), renders whatever the server says.
- **Server-owned state machine:** WAITING, then per round DISCUSS and VOTE, then RESULTS.
  The server owns the timers and sends `seconds_left`; clients never advance state.
- **Waiting room:** the number of human slots comes from `config.yml`.
  When all are filled, labels (Player A/B/C) are shuffled across the slots
  and AI agents take the remaining ones.
- **Blind condition:** the participant type (`human`/`ai`) is stored only in MongoDB.
  No WebSocket payload contains it. AI agents post and vote through the same
  server methods as humans, and see only public information.
- **AI agents:** provider interface (`agents/base.py`) with an LLM provider
  (any OpenAI-compatible API, default Gemini Flash-Lite) and a scripted fallback.
  Agents have a human-like delay, can stay silent, and never speak twice in a row.
  A system prompt keeps replies short and casual and never reveals what they are.

## Design decisions

- **Round 1 feedback:** configurable, default [tally / none]. Nobody sees who voted for whom.
- **Final result:** based on the last round's votes. Round 1 is a first poll.
- **Ties:** broken randomly, or by round 1 votes (`tie_break: round1`).
- **Self-votes** are allowed, votes can be changed until the phase ends, abstentions are not counted.
- **Waiting room** shows no player counts, so the number of humans (and AIs) isn't revealed.
- **Reconnect:** a page refresh restores the same seat, phase, history and vote.

## Trade-offs and known limitations

- Active sessions are held in memory. A backend restart ends them (finished data stays in MongoDB).
- A disconnected human is treated as an abstention. No replacement or pausing.
- No authentication. A participant is identified by a per-tab id.
- Free LLM tier has request limits, so agents reply slowly by design and fail silent on API errors.
  Failed votes fall back to a simple scripted vote so sessions never stall.
- Plain UI, no styling polish, no automated tests (manual testing of all 3 conditions).

## Time and scope

The brief says about 2 hours, with 4 hours as the maximum (Section 4 says "4-hour").
Actual time spent: >3 hours.

## AI usage

All prompts and tools are logged in `ai_logs/ai_logs.md`.