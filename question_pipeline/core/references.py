"""Existing Eigen questions saved by `fetch-references`, grouped by topic."""
import json

from . import store

REFERENCES_DIR = store.DATA_DIR / "references"

# Short tags used in Eigen's data, mapped to one name so "mech" and "mechanics" are the same topic
TOPIC_ALIASES = {"mech": "mechanics", "math": "maths"}


def _topic_names(topics: str | None) -> list[str]:
    names = [t.strip().lower() for t in (topics or "").split(",") if t.strip()]
    return [TOPIC_ALIASES.get(n, n) for n in names]


def load_references() -> list[dict]:
    return [
        {**json.loads(p.read_text(encoding="utf-8")), "_file": p.name}
        for p in sorted(REFERENCES_DIR.glob("q*.json"))
    ]


def list_topics() -> dict[str, int]:
    """Every topic (and subject like 'physics') with how many reference questions it has."""
    counts: dict[str, int] = {}
    for ref in load_references():
        for name in _topic_names(ref.get("topics")):
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def find_references(topic: str) -> list[dict]:
    wanted = TOPIC_ALIASES.get(topic.strip().lower(), topic.strip().lower())
    return [ref for ref in load_references() if wanted in _topic_names(ref.get("topics"))]
