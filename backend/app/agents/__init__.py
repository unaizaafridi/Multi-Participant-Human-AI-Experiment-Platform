import logging

from .scripted import ScriptedProvider

log = logging.getLogger("agents")


def make_provider(config: dict):
    """Returns a NEW provider instance (each AI agent keeps its own memory)."""
    name = config["ai"]["provider"]
    if name == "llm":
        log.warning("LLM provider not implemented yet, using scripted instead")
    return ScriptedProvider()