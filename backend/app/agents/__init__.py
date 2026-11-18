import logging
import os

from .scripted import ScriptedProvider

log = logging.getLogger("agents")


def make_provider(config: dict):
    """Returns a NEW provider instance (each AI agent keeps its own memory)."""
    ai = config["ai"]
    if ai["provider"] == "llm":
        key_env = ai.get("api_key_env", "GEMINI_API_KEY")
        if os.environ.get(key_env):
            from .llm import LLMProvider
            return LLMProvider(config)
        log.warning("ai.provider is 'llm' but %s is not set; using scripted", key_env)
    return ScriptedProvider()