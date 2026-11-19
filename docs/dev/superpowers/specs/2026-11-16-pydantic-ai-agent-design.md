# Agent in Python on pydantic-ai, run as a Tauri sidecar

Date: 2026-11-16. Status: approved.

## Intent

Move everything agent-related out of the Rust backend into a Python package built on
[pydantic-ai](https://pydantic.dev/docs/ai/overview/) and
[pydantic-ai-harness](https://pydantic.dev/docs/ai/harness/). Rust keeps the app: SQLite,
settings, projects, chats, skill discovery, lessons storage, the file pane, and relaying
events to the UI.

The port is not a translation of the Rust code. Where pydantic-ai or the harness already does
a job (tool errors and retries, argument validation, unknown tools, loop detection, output
caps, approvals, cancellation, history repair, file tools, shell, skills, MCP), use it and
delete our version. Write our own code only for what Thea does that the framework does not:
the research, ledger, docket and STE tools, `TASK.md` rounds, reflection, and the stdio bridge.

A fresh start; the `feat/python-agent` branch (OpenAI Agents SDK) is not a base.

## Goals

- Same user-visible workflow as `main`: personas, skills, `TASK.md` checklist and rounds,
  approvals, reflection lessons, research and docket tools, evals.
- The frontend does not change. Python emits the same events with the same payloads.
- Rust stores every message and lesson. Python never opens SQLite.
- macOS and Windows installers still build on one Mac with `just build`.
- Less code than today: each hand-written guard in `agent/mod.rs` either maps to a framework
  feature or is justified in this doc.

## Non-goals

- New agent features. Tool names and arguments change only where the harness tools differ
  (see 4.3); skills and `how-you-work.md` are edited to match.
- Tracing. pydantic-ai has `instrument=True` / Logfire; add later.
- Talking to the agent from outside the app.

## Anti-goals

- A network port. The sidecar talks over stdin/stdout only.
- Two sources of truth for chat history.
- Hand-written versions of framework features "because the Rust code had one".

## Constraints

- Python with uv only; `agent/uv.lock` committed. Python 3.13.
- `pydantic-ai-harness` is 0.x: its API may change between minor releases. Pin exact versions
  of `pydantic-ai-slim`, `pydantic-ai-harness` and `pydantic-evals` (2.68.0 / 0.68.0 / 2.68.0
  at time of writing) and upgrade deliberately.
- The Windows installer is cross-built on macOS with `cargo-xwin`; PyInstaller cannot
  cross-build.
- Ollama's OpenAI-compatible `/v1` endpoint, which pydantic-ai's `OllamaModel` uses, cannot set
  the context size (`num_ctx`). See 4.1.
- Docs under `docs/` pass the ASD-STE100 check; that check moves to Python with `tools/ste.rs`.

## Approaches

| | How | Trade-off |
|---|---|---|
| **A. Sidecar over stdio (chosen)** | Tauri spawns `thea-agent`; JSON lines both ways. | No port, no auth, UI unchanged, Rust restarts it on crash. Cost: a small protocol, and bundling Python. |
| B. Local HTTP server, UI over SSE | FastAPI next to Tauri. | Conventional, but a localhost port needs a token, persistence splits, IPC layer changes. |
| C. Embed Python with PyO3 | One process. | Async bridging, GIL and Windows cross-build cost more than the port. Dropped. |

The owner picked A.

## Design

### 1. Split of responsibilities

| Moves to `agent/` (Python) | Stays in `src-tauri/` (Rust) |
|---|---|
| `agent/*`, `providers/*`, `tools/*`, `mcp.rs`, `approvals.rs`, `bin/eval.rs` | `db.rs`, settings, personas, projects, chats, knowledge files |
| | `skills.rs` (discovery, for the Skills pane), `templates.rs`, `lessons.rs` |
| | file-pane commands, `sidecar.rs` (new): spawn, relay, restart |

Rust commands that used the moved code (`send_user_message`, `stop_chat_generation`,
`respond_to_approval`, `rate_message`, `list_provider_models`, `get_model_capabilities`,
`test_provider_connection`, `test_mcp_server`) keep their names and signatures and forward to
the sidecar.

### 2. Protocol (JSON lines)

One long-lived process; several chats can run turns at once. Each line is one JSON object
with `type`. Pydantic models define them on the Python side (`thea_agent/protocol.py`); serde
structs mirror them in `sidecar.rs`; shared fixtures in `agent/tests/fixtures/protocol/` are
round-tripped on both sides.

Rust → Python:

- `turn`: `chat_id` plus everything Rust resolves: persona, provider (`protocol`, `base_url`,
  `api_key`, `model`), `small_model` override, workspace (`id`, `name`, `root_path`,
  `instructions`, `is_chat`), knowledge files, skill libraries (paths plus the enabled skill
  names for this persona), MCP servers, settings Python needs, lessons, stored history.
- `approval`: `request_id`, `decision` (`approve` | `always_allow_project` | `reject`).
- `cancel`: `chat_id`.
- `call`: `id`, `method`, `params` for `list_models`, `model_capabilities`, `test_provider`,
  `test_mcp_server`, `reflect_rating`.

Python → Rust:

- `event` with `name` and `payload`. UI events are relayed unchanged: `chat:delta`,
  `agent:tool-event`, `agent:approval-request`, `agent:round`, `agent:incomplete`,
  `agent:prompt-size`, `chat:finished`. `message` (a row to insert) and `lesson` (a lesson to
  append) are stored by Rust, not relayed.
- `result`: `id`, `ok`, `value` or `error`, answering a `call`.

Python emits `chat:finished` once per turn, with `error` set on failure or cancel. If the
process exits, Rust emits `chat:finished` with an error for every running chat and respawns
on the next request. Stderr goes to `~/.thea/logs/agent.log`.

### 3. History

Each stored message row gets a new nullable column, `model_message_json`: the pydantic-ai
`ModelMessage` serialized with `ModelMessagesTypeAdapter`. Python sends it on every `message`
event; Rust stores it next to the existing `role` / `content` / `tool_calls_json` columns,
which the UI keeps reading. On the next turn Python rebuilds history from
`model_message_json`, losslessly, and passes it through `repair_messages`, which closes tool
calls a cancelled turn left without results. Rows from before the migration have no JSON and
are replayed as plain user and assistant text.

This replaces `history_items` / `replay_history` and the hand-written dropping of orphan calls.

### 4. The turn

#### 4.1 Models

- OpenAI-compatible providers: `OpenAIChatModel` with `OpenAIProvider(base_url, api_key)`.
- Ollama: `OllamaModel` with `OllamaProvider(base_url=<base>/v1)`.
- Native thinking: off unless `persona.native_thinking`, through the model settings'
  `thinking` field, which pydantic-ai maps per provider.
- Tier: `/api/show` (Ollama) for parameter size and capabilities, as today, via `httpx`.
  `PromptBudget.for_tier` stays as a small dataclass; `persona.max_steps` overrides the step
  cap.
- Context size: decided, `OllamaModel` on `/v1` as is. Thea's context-size setting no longer
  applies to Ollama; the user sets `OLLAMA_CONTEXT_LENGTH` on the Ollama server, and
  `docs/how-to/connect-providers.md` says so. The setting is removed from the Ollama path.
- Models without tool calling: not supported for agent work. The Rust text `<tool_call>`
  fallback is dropped (`gemma4:e4b`, the target, calls tools natively). A model whose profile
  or `/api/show` says no tools gets no tools and chats only. *(My call.)*

#### 4.2 One agent, capabilities instead of a hand-written loop

One `pydantic_ai.Agent` per turn, `deps_type=TurnDeps` (emit, approvals, budget, workspace
root, signals for reflection), `instructions` = the system prompt as `build_system_prompt`
writes it today minus the parts the capabilities now supply (skills catalog, tool lists).

| Today (Rust) | Now |
|---|---|
| Errors returned to the model as text | Tools raise `ToolFailed` (call done, it failed: adapt) or `ModelRetry` (fix the call). Neither ends the run. `ToolFailed` does not use the retry budget. |
| `missing_args_error`, string-to-number coercion | Pydantic validation of the tool signature; a validation error goes back to the model as a retry with the details. Lax mode coerces `"1"` to `1`. |
| `not_found_message` for invented tool names | Built in: an unknown tool is answered with the list of available tools. |
| `REPEAT_LIMIT` refusal of repeated failing calls | `DetectLoops()` (harness), default `action='nudge'`. |
| `cap_tool_output` | `ToolOutputLimits(bands=[Band(over=tool_output_chars, action=Truncate())])`. Truncate, not Spill, so nothing is written into the user's project. |
| `MAX_STEPS` and the separate wrap-up call | `UsageLimits(request_limit=max_steps)` plus a `WrapUpNearRequestLimit` capability (the pattern in the docs): a request-scoped prompt when few requests are left, and no tools on the last one, so the model writes its status itself. |
| `TASK.md` nudges, `MAX_NUDGES`, empty-reply nudge | An output validator: if the run used tools and `TASK.md` has open items (or the reply is empty), raise `ModelRetry` with today's nudge text; `retries={'output': MAX_NUDGES}`; past the last nudge it accepts the reply. |
| `CancellationToken` per chat | pydantic-ai `CancellationToken` passed to the run; `cancel` triggers it; a new `turn` for the same chat cancels the old one. |
| Unexpected exceptions in tools | One `on_tool_execute_error` hook turns `OSError` and `httpx.HTTPError` into `ToolFailed`; anything else is a bug and fails the turn with `chat:finished.error`. *(My call.)* |
| `preload_skill`, `load_skill`, skill-not-tool hints | `Skills(...)` (harness), one library per skill source, each with its own `LocalWorkspaceBackend`, narrowed to the persona's enabled skills. The model loads a skill with `load_capability`. |
| `sequentialthinking` thought cap and argument repair | The `sequential-thinking` MCP server stays as an ordinary server. Validation retries replace the repair; a `PrepareTools` check hides it after `MAX_THOUGHTS` calls in the run. |

`MAX_ROUNDS` stays ours: a round is one run. When a run hits the request limit and `TASK.md`
still has open items, the next run starts with a fresh history of one user message, today's
round brief (request, last status, `TASK.md`), and `agent:round` is emitted. The harness
compaction capabilities were considered and not used: rounds are part of Thea's research
method (notes and ledger on disk carry knowledge across rounds), not just context management.

#### 4.3 Tools

| Group | Source |
|---|---|
| `read_file`, `write_file`, `edit_file`, `list_directory`, `search_files`, `find_files` | `FileSystem()` (harness) on `LocalWorkspace(root)`. Path containment, symlink checks and binary handling are built in. `read_only_patterns=['research/sources.json', 'docket/docket.json']` replaces the Rust refusals. Replaces `tools/fs.rs` and `sandbox.rs`. |
| `run_command` | `Shell()` (harness). Replaces `tools/shell.rs`. |
| MCP servers | `MCPToolset(StdioTransport(...), tool_error_behavior='failed', max_retries=...)`, `.prefixed('mcp__<server>')`. A server that fails to start is skipped with a log line. Server stderr to `~/.thea/logs/mcp.log`. |
| `web_search` (SearXNG), `fetch_url` (SSRF protection, PDF text), `lookup_paper` | Our function tools. `WebFetch(local=True)` was checked: its docs state domain filters but no private-address (SSRF) guard, so `fetch_url` stays ours. |
| `add_source`, `list_sources`, `check_citations`, `add_docket_item`, `update_docket_item`, `list_docket`, `export_calendar`, `check_style` | Our function tools, ported from `ledger.rs`, `docket.rs`, `ste.rs`, raising `ToolFailed` / `ModelRetry` as above. |

Renames from today: `list_dir` → `list_directory`, `search` → `search_files`, `load_skill` →
`load_capability`; `edit_file` takes `old_text` / `new_text`. Skills and `how-you-work.md`
are updated to these names.

#### 4.4 Approvals

The deferred-tools flow, resolved inline:

- File writes and commands: `Permissions('read-only')` (harness) holds every `FileSystem`
  write and every `Shell` command for approval.
- Our mutating tools (`add_source`, docket tools, `export_calendar`) and MCP tools of servers
  without `auto_approve`: `requires_approval=True`, or `ApprovalRequired(metadata=...)` raised
  from the tool when it needs to show a diff.
- `HandleDeferredToolCalls(handler)`: for each held call, emit `agent:approval-request`
  (summary, details, diff from the request metadata), await the `approval` message, and
  return `DeferredToolResults`. `ask_permissions` serves the `Permissions` calls.
- "Always allow for this project": a per-project set of categories (`write`, `shell`, `mcp`)
  held in the sidecar for the session, checked before asking, as `approvals.rs` does today.
  For `Permissions` it is passed as its `remembered` set.

A rejected call returns "the user denied it" to the model, as the framework does.

#### 4.5 Events

`agent.iter()` (or `event_stream_handler`) maps the framework's stream events to today's UI
events: text deltas → `chat:delta`; function tool call and result events →
`agent:tool-event` (`running`, then `done` / `error` / `rejected` from the result's
outcome); each completed `ModelRequest` / `ModelResponse` → a `message` event with both the UI
row and `model_message_json`; request size → `agent:prompt-size`. `agent:incomplete` is
emitted when the last round ends with `TASK.md` items open.

#### 4.6 Reflection

As today: one reflection per turn, only on a real signal (last `check_citations` /
`check_style` result, or repeated tool errors read from the run's `ToolReturnPart` outcomes),
plus ratings through `reflect_rating`. One small `Agent` with a plain-text output writes at
most one lesson, emitted as a `lesson` event.

### 5. Package and bundling

- `agent/` is a uv project: `src/thea_agent/`, run as `python -m thea_agent` (the stdio
  server). Dependencies: `pydantic-ai-slim[openai,mcp]`, `pydantic-ai-harness`, `httpx`,
  `pypdf`. Dev: `pytest`, `pytest-asyncio`, `ruff`, `pydantic-evals`.
- Runtime bundle *(my call)*: a `python-build-standalone` CPython 3.13 per target, plus the
  locked dependencies installed with `uv pip install --python-platform <triple> --target ...`
  (wheels only, so the Windows bundle builds on macOS), shipped as a Tauri `resources` folder.
  `sidecar.rs` runs `<resources>/python/bin/python3 -m thea_agent` (`python.exe` on Windows).
  `just bundle-agent <triple>` builds it; `build-macos` and `build-windows` call it first.
  Adds about 40–60 MB per installer. Builds are unsigned today; signing later must cover the
  `.so` / `.dylib` files in the bundle.
- Dev: `sidecar.rs` runs `uv run --project agent python -m thea_agent` in debug builds.

### 6. Rust after the move

Delete `agent/`, `providers/`, `tools/`, `mcp.rs`, `approvals.rs`, `bin/eval.rs` and unused
crates. Add `sidecar.rs` and the `model_message_json` migration. `AppState` loses the approval
gate and cancel tokens and gains the sidecar handle.

### 7. Evals

`python -m thea_agent.eval --model ... --cases evals/research` replaces the Rust binary: same
case JSON, same scores (citations pass, sources, style violations per 100 words, thought
steps), same results path. `pydantic-evals` holds the dataset and evaluators; cases run in a
temp workspace with a recording emit and an auto-approve handler.

### 8. Repo wiring

- `justfile`: `setup`, `test`, `lint`, `fmt`, `eval` gain the Python steps (`uv sync --locked`,
  `pytest`, `ruff check`, `ruff format`).
- ADR `docs/dev/adr/0001-python-agent-sidecar.md` (Nygard) records approach A and the choice
  of pydantic-ai plus the harness.
- `docs/dev/explanation/architecture.md` and the user docs that name tools updated.
- `CHANGELOG.md` entry under Unreleased.

## Testing

- Our tools: unit tests ported from the Rust tests (ledger, docket, STE, SSRF guard).
- Turn behaviour with `FunctionModel` / `TestModel`: `TASK.md` nudge via output retry, round
  rollover at the request limit, wrap-up on the last request, approval approve / reject /
  always-allow, cancel mid-tool, history round-trip through `model_message_json`.
  Framework features (validation retries, loop detection, output truncation) get one smoke test
  each that they are wired in, not re-tests of the framework.
- Protocol fixtures round-tripped on both sides.
- One end-to-end smoke: Rust spawns the dev sidecar, sends a turn backed by `TestModel`, and
  sees `message` rows land and `chat:finished` arrive.
- Manual: `just run` against Ollama `gemma4:e4b`; one research and one assistant eval case.

## Left to the builder

- Exact `turn` request fields beyond those named.
- Module layout inside `thea_agent/`.
- `iter()` versus `event_stream_handler` for events.
- Order of work, keeping `just check` green at each step.
