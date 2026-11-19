# System Architecture

This guide explains the 3-part architecture of Thea.

Thea is a desktop application with 3 parts:

- **Frontend (`src/`)**: A `React 19` and `TypeScript` user interface with `Zustand` state in `src/stores/useAppStore.ts`. It shows 3 panes: the left sidebar, the center chat view, and the right pane with `Artifacts` and `Files`.
- **Rust app (`src-tauri/src/`)**: A `Tauri 2` process. It owns the `SQLite` database (`db.rs`), settings, projects, and chats. It also finds skills (`skills.rs`) and stores lessons (`lessons.rs`). Other code serves the file pane (`files.rs`) and the sidecar (`sidecar.rs`).
- **Python agent (`agent/`)**: The `thea-agent` process. It runs the agent on `pydantic-ai` and `pydantic-ai-harness`. It never opens `SQLite`, and it has no network port.

The frontend calls the Rust app through `Tauri` `invoke` commands (`src/lib/ipc.ts`). The Rust app starts the agent as a sidecar process. The two exchange `JSON` lines on `stdin` and `stdout`.

During a turn, Rust builds a `turn` request from the database. The agent returns events, and Rust relays them to the frontend. The events are `chat:delta`, `agent:tool-event`, `agent:approval-request`, `agent:round`, `agent:incomplete`, and `chat:finished`. Each message and each lesson goes into the database through Rust. If the agent process stops, Rust starts it again.

The release installers bundle a `CPython 3.13` runtime from `python-build-standalone`. The `just bundle-agent <triple>` recipe builds it into `agent/dist/python`. The design reason is in [ADR 0001](../adr/0001-python-agent-sidecar.md).

## Code Map

Rust app:

- `src-tauri/src/sidecar.rs`: starts the agent, relays the `JSON` lines, restarts the agent, and tracks pending calls.
- `src-tauri/src/turn_request.rs`: builds the `turn` request from the database.
- `src-tauri/src/lessons.rs`: stores lessons and chooses the lessons for a prompt.

Python agent (`agent/src/thea_agent/`):

- `__main__.py`: the `stdio` server. It reads requests and starts handlers.
- `protocol.py`: the types of the `JSON` lines. Tests round-trip fixtures against the Rust types.
- `turn.py`: one turn. It runs up to `MAX_ROUNDS` rounds and maps the event stream to UI events.
- `history.py`: converts stored message rows to `pydantic-ai` messages and back.
- `toolsets.py`: builds the tools of a turn: file tools, shell, skills, domain tools, and `MCP` servers.
- `capabilities.py`: `TASK.md` nudges (`MAX_NUDGES`), the wrap-up request, the thought cap, and tool errors.
- `approvals.py`: the approval gate for `write`, `shell`, and `mcp` calls.
- `models.py`: model objects, model capabilities, and tier budgets.
- `prompt.py` and `how-you-work.md`: the system prompt.
- `reflection.py`: lessons from citation checks, ratings, and tool errors.
- `eval.py`: runs a case of the evaluation with no user interface, and scores it. `promptfoo` calls it through `evals/promptfoo/provider.py`.
- `tools/ledger.py`: the source ledger and `check_citations`.
- `tools/docket.py`: the docket (`docket/docket.json`, `docket/DOCKET.md`) and `export_calendar` (`.ics`).
- `tools/research.py`: `web_search`, `fetch_url` with `SSRF` protection, and `lookup_paper`.
- `tools/notes.py`: `add_note`, which adds one note under a heading of a notes file.
