"""Per-turn dependencies handed to every tool through `RunContext`."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_ai import ToolFailed

from thea_agent.emit import Emit

if TYPE_CHECKING:
    from thea_agent.approvals import Approvals

_PATH_NOISE = "`*\"',;_ \t\r\n"


@dataclass
class Signals:
    """Last verdict of each check tool, read by the reflection step."""

    citations: tuple[bool, str] | None = None


@dataclass
class TurnDeps:
    root: Path | None
    emit: Emit
    chat_id: str
    signals: Signals = field(default_factory=Signals)
    settings: dict = field(default_factory=dict)
    project_id: str = ""
    # A project turn works from TASK.md; a plain chat does not.
    checklist: bool = False
    # ask_user was called: the reply is a question, so the turn ends and waits for the answer.
    asked: bool = False
    search_results: int = 8
    tool_output_chars: int = 12000
    # None: nobody to ask, so held calls stay unapproved.
    approvals: "Approvals | None" = None

    def resolve(self, user_path: str) -> Path:
        """Resolve a model-supplied path inside the workspace; refuse anything that escapes it."""
        if self.root is None:
            raise ToolFailed("No workspace is open for this chat")
        # Small models leak markdown into path arguments: `a.md`, **a.md**, "a.md",
        cleaned = user_path.strip(_PATH_NOISE)
        root = self.root.resolve()
        path = (
            root / cleaned
        ).resolve()  # absolute `cleaned` replaces root; symlinks followed
        if not path.is_relative_to(root):
            raise ToolFailed(f"Path '{cleaned}' escapes project workspace '{root}'")
        return path
