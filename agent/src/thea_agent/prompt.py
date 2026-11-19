"""The system prompt (`instructions`) of one turn. Skills and tools are listed by their capabilities."""

import os
from pathlib import Path

from thea_agent.models import PromptBudget
from thea_agent.protocol import TurnRequest

HOW_YOU_WORK = (Path(__file__).parent / "how-you-work.md").read_text(encoding="utf-8")

CHAT_PROMPT = """## Chat
Answer the user directly, in short, plain sentences.
- For facts that you are not sure of, or that change over time, use web_search, then read the best page with fetch_url.
- Use read_file to read a file in this chat's folder.
- When the user asks you to save the conversation or a summary, write it as a Markdown file in this chat's folder with write_file.

"""

_EXCLUDED = {".git", "node_modules", "target", ".venv"}


def _excluded(name: str) -> bool:
    return name in _EXCLUDED or name.startswith(".env")


def workspace_tree(root: Path, max_entries: int, max_depth: int = 3) -> list[str]:
    """Top entries of the workspace, breadth of `os.walk`, directories with a trailing `/`."""
    # ponytail: no .gitignore handling (the Rust walker had it); the exclude list covers the big ones.
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts) + 1
        dirnames[:] = sorted(d for d in dirnames if not _excluded(d))
        entries = [(d, True) for d in dirnames] + [
            (f, False) for f in sorted(filenames) if not _excluded(f)
        ]
        for name, is_dir in entries:
            out.append((rel / name).as_posix() + ("/" if is_dir else ""))
            if len(out) >= max_entries:
                return out
        if depth >= max_depth:
            dirnames[:] = []
    return out


def _read_knowledge(root: Path, path: str) -> tuple[str, str] | None:
    """(display path, text) of a pinned file inside the workspace, or None if it cannot be read."""
    full = (root / path).resolve()
    if not full.is_relative_to(root.resolve()) or _excluded(full.name):
        return None
    try:
        if full.stat().st_size > 512 * 1024:
            return None
        return full.relative_to(root.resolve()).as_posix(), full.read_text(
            encoding="utf-8"
        )
    except (OSError, UnicodeDecodeError):
        return None


def build_system_prompt(
    req: TurnRequest, tool_names: list[str], budget: PromptBudget
) -> str:
    p = req.persona
    prompt = (
        "You are Thea, a desktop AI assistant by ThetaPlex running on local models.\n"
    )
    prompt += (
        f"## Active Persona: {p.name} ({p.tagline})\n{p.system_prompt}\n\n"
        if p
        else CHAT_PROMPT
    )
    prompt += (
        "When creating standalone HTML prototypes, visualizations, or code demos, you can wrap them in "
        "fenced code blocks (e.g. ```html ... ```) so the user can preview them live in the Artifacts pane.\n"
    )
    # The TASK.md workflow is for projects; a plain chat just answers.
    if p and "write_file" in tool_names:
        prompt += f"\n{HOW_YOU_WORK}"

    ws = req.workspace
    if ws is not None:
        if ws.is_chat:
            prompt += f"\n## Workspace\nThis chat has no project. Its own workspace folder is `{ws.root_path}`.\n"
        else:
            prompt += (
                f"\n## Active Project: {ws.name}\nWorkspace root: `{ws.root_path}`\n"
            )
        if ws.instructions.strip():
            prompt += f"\n### Project Instructions\n{ws.instructions.strip()}\n"
        root = Path(ws.root_path)
        if root.is_dir():
            if tree := workspace_tree(root, budget.tree_entries):
                prompt += (
                    "\n### Workspace File Tree (top entries)\n```\n"
                    + "".join(f"{e}\n" for e in tree)
                    + "```\n"
                )
            if req.knowledge_files:
                prompt += "\n### Pinned Project Knowledge Files\n"
                for kf in req.knowledge_files:
                    if found := _read_knowledge(root, kf):
                        rel, text = found
                        prompt += f"\n#### File: `{rel}`\n```\n{text[: budget.knowledge_chars]}\n```\n"

    prompt += f"\n## Budget\nTool steps this turn: {budget.max_steps}."
    if "add_source" in tool_names:
        prompt += (
            f" web_search returns {budget.search_results} results. Per round, register and read at most "
            f"{budget.min_sources} to {budget.max_sources} sources, then write notes. "
            "The task's source target is in TASK.md."
        )
    prompt += "\n"

    kept = [t.strip() for t in req.lessons if t.strip()]
    lessons = "\n".join(f"{i}. {t}" for i, t in enumerate(kept, 1))
    if lessons:
        prompt += f"\n## Lessons from earlier sessions\n{lessons}\n"
    return prompt
