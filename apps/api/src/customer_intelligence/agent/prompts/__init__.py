"""Versioned system prompts. Edit by adding a new `<name>.v<N>.md` file and bumping ACTIVE."""

from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from pathlib import Path

PROMPT_DIRECTORY = Path(__file__).resolve().parent
# Pinned versions keep traces and eval results comparable across prompt edits.
ACTIVE = {
    "assistant": 5,
    "inspection": 1,
    "structured_guard": 1,
    "eval_judge": 1,
    "investigator_plan": 1,
    "investigator_followup": 1,
    "investigator_write": 1,
    "account_notes": 3,
    "daily_brief": 3,
}


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    text: str

    @property
    def label(self) -> str:
        """Stable identifier recorded on traces, e.g. `assistant@v1+3f2a9c1d`."""
        digest = sha256(self.text.encode("utf-8")).hexdigest()[:8]
        return f"{self.name}@v{self.version}+{digest}"


@cache
def load_prompt(name: str, version: int | None = None) -> Prompt:
    selected = version if version is not None else ACTIVE[name]
    path = PROMPT_DIRECTORY / f"{name}.v{selected}.md"
    return Prompt(name, selected, path.read_text(encoding="utf-8").strip())


def inline_label(text: str) -> str:
    """Label for instructions that live beside their service rather than in the registry."""
    return "inline+" + sha256(text.encode("utf-8")).hexdigest()[:8]
