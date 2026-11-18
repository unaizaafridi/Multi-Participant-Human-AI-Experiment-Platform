from typing import Protocol


class AIProvider(Protocol):
    """Anything that can play one AI participant.

    ctx contains only public information:
      you:      this agent's label, e.g. "Player A"
      players:  all three labels
      round:    current round number
      messages: public chat history, a list of {"from", "text", "round", ...}
      round1_tally: dict label -> votes, only in later rounds (else None)
    """

    async def generate_message(self, ctx: dict) -> str | None:
        """Return the next chat message, or None to stay quiet this time."""
        ...

    async def decide_vote(self, ctx: dict) -> str:
        """Return the label of the player to vote for."""
        ...