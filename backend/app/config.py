import os
import yaml

VALID_TYPES = {"human", "ai"}
VALID_PROVIDERS = {"scripted", "llm"}
VALID_FEEDBACK = {"none", "tally"}
VALID_TIE_BREAK = {"random", "round1"}

DEFAULTS = {
    "session": {"rounds": 2, "discussion_seconds": 60, "vote_seconds": 20},
    "results": {"round1_feedback": "none", "tie_break": "random"},
    "ai": {"provider": "scripted", "min_delay_seconds": 2, "max_delay_seconds": 6},
}


def _merge_defaults(cfg: dict) -> dict:
    for section, values in DEFAULTS.items():
        cfg.setdefault(section, {})
        for key, value in values.items():
            cfg[section].setdefault(key, value)
    return cfg


def validate_config(cfg: dict) -> dict:
    cfg = _merge_defaults(cfg)
    s, r, a = cfg["session"], cfg["results"], cfg["ai"]

    participants = s.get("participants")
    if not isinstance(participants, list) or len(participants) != 3:
        raise ValueError("session.participants must be a list of exactly 3 entries")
    if any(p not in VALID_TYPES for p in participants):
        raise ValueError(f"participant types must be one of {sorted(VALID_TYPES)}")
    if "human" not in participants:
        raise ValueError("at least one participant must be human")

    for key in ("rounds", "discussion_seconds", "vote_seconds"):
        if not isinstance(s[key], int) or s[key] <= 0:
            raise ValueError(f"session.{key} must be a positive integer")

    if r["round1_feedback"] not in VALID_FEEDBACK:
        raise ValueError(f"results.round1_feedback must be one of {sorted(VALID_FEEDBACK)}")
    if r["tie_break"] not in VALID_TIE_BREAK:
        raise ValueError(f"results.tie_break must be one of {sorted(VALID_TIE_BREAK)}")

    if a["provider"] not in VALID_PROVIDERS:
        raise ValueError(f"ai.provider must be one of {sorted(VALID_PROVIDERS)}")
    if a["min_delay_seconds"] < 0 or a["max_delay_seconds"] < a["min_delay_seconds"]:
        raise ValueError("ai delays must satisfy 0 <= min_delay_seconds <= max_delay_seconds")

    return cfg


def load_config() -> dict:
    path = os.environ.get("CONFIG_PATH", "config.yml")
    with open(path) as f:
        raw = yaml.safe_load(f)
    return validate_config(raw)


if __name__ == "__main__":
    cfg = load_config()
    p = cfg["session"]["participants"]
    print("Config OK")
    print(f"  humans: {p.count('human')}  ai: {p.count('ai')}")
    print(f"  full config: {cfg}")