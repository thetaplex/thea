# Agent in Python on pydantic-ai — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Rust agent (loop, providers, tools, MCP, approvals, eval) with a Python sidecar on pydantic-ai and pydantic-ai-harness, with no frontend change.

**Architecture:** Tauri spawns `python -m thea_agent` and talks JSON lines over stdin/stdout. Python runs each turn as pydantic-ai agent runs (one run per round) built from framework capabilities plus Thea's own domain tools, and emits UI events plus `message` / `lesson` events that Rust stores in SQLite.

**Tech Stack:** Python 3.13, uv, pydantic-ai-slim[openai,mcp] 2.68.0, pydantic-ai-harness[skills] 0.68.0, pydantic-evals 2.68.0, httpx, pypdf, pytest, pytest-asyncio, ruff; Rust/Tauri 2 for `sidecar.rs`.

**Spec:** `docs/dev/superpowers/specs/2026-11-16-pydantic-ai-agent-design.md`

## Global Constraints

- Python with uv only (`uv add`, `uv run`, `uv sync --locked`); commit `agent/uv.lock`. Never pip, never activate a venv.
- Pin exact: `pydantic-ai-slim[openai,mcp]==2.68.0`, `pydantic-ai-harness[skills]==0.68.0`, `pydantic-evals==2.68.0`.
- No network port. Python never opens SQLite. The frontend (`src/`) does not change.
- UI event names and payload fields are exactly today's: `chat:delta {chat_id, delta}`, `agent:tool-event {chat_id, tool_call_id, tool_name, arguments, status: running|done|rejected|error, output, artifact_path}`, `agent:approval-request {request_id, chat_id, project_id, tool_name, summary, details, diff}`, `agent:round {chat_id, round, max_rounds}`, `agent:incomplete {chat_id, reason, open_items}`, `agent:prompt-size {chat_id, chars}`, `agent:first-prompt {messages, tools}`, `chat:finished {chat_id, error}`.
- Approval decisions: `approve` | `always_allow_project` | `reject`; categories `write` (FileSystem writes, `add_docket_item`, `update_docket_item`, `export_calendar`), `shell` (`run_command`), `mcp` (servers without `auto_approve`).
- Constants carried over: `MAX_ROUNDS = 6`, `MAX_NUDGES = 4`, `MAX_THOUGHTS = 5`, `TASK_FILE = "TASK.md"`, budgets from `PromptBudget::for_tier` (`src-tauri/src/agent/mod.rs:84-121`) verbatim.
- Nudge, wrap-up and round-brief texts copied verbatim from `src-tauri/src/agent/task.rs` and `agent/mod.rs` (`WRAP_UP`, `round_brief`).
- Docs under `docs/` outside `docs/dev/superpowers/` pass the STE check (ported in Task 2).
- Every task leaves `just check` green.

## Review Focus

1. **Cancel while an approval is pending** (user hits stop, or sends a new message): the pending future is cancelled, no tool runs, exactly one `chat:finished` for that turn. → test in Task 6.
2. **Sidecar dies mid-turn:** every running chat gets `chat:finished` with an error; the next send respawns the process. → test in Task 7.
3. **Chats created before the migration** (rows with `tool_calls_json` but no `model_message_json`, including a cancelled call with no result): next turn replays them as text and the provider is not sent an orphan tool call. → test in Task 6.
4. **Send while a turn is running in the same chat:** the old run is cancelled, each turn emits its own single `chat:finished`. → test in Task 6.
5. **An MCP server that fails to start or a malformed stdin line:** the server is skipped with a log line and the turn continues; a bad line is logged and ignored, the process keeps serving. → tests in Tasks 1 and 5.

---

## File Structure

```
agent/
  pyproject.toml, uv.lock, .python-version (3.13)
  src/thea_agent/
    __main__.py        stdio server: read lines, dispatch, write lines
    protocol.py        pydantic models for every line type
    emit.py            Emit type + stdout writer (one lock, one line per event)
    models.py          build_model, list_models, model_capabilities, tier, budget
    prompt.py          build_system_prompt, how-you-work.md
    capabilities.py    TaskNudge, WrapUpNearRequestLimit, ThoughtCap, ToolErrors
    approvals.py       Approvals + deferred-call handler
    toolsets.py        assemble FileSystem/Shell/Skills/MCP/domain tools per turn
    history.py         stored rows <-> ModelMessage, message events
    turn.py            run_turn: rounds, events, reflection signal
    reflection.py      reflect(), detect_repeated_errors()
    tools/ ste.py ste_words.py ledger.py docket.py research.py
    eval.py            pydantic-evals runner
  tests/ (one test file per module) + fixtures/protocol/*.json
src-tauri/src/sidecar.rs (new); db.rs, lib.rs (modified); agent/, providers/, tools/, mcp.rs, approvals.rs, bin/eval.rs (deleted)
```

---

### Task 1: Package, protocol, stdio server

**Files:**
- Create: `agent/pyproject.toml`, `agent/.python-version`, `agent/src/thea_agent/{__init__,__main__,protocol,emit}.py`, `agent/tests/test_protocol.py`, `agent/tests/fixtures/protocol/{turn,approval,cancel,call,event,result}.json`
- Modify: `justfile` (`setup`, `test`, `lint`, `fmt`), `.gitignore` (`agent/.venv`)

**Interfaces:**
- Produces: `protocol.TurnRequest`, `Approval`, `Cancel`, `Call`, `Event`, `Result`, `Incoming = Annotated[TurnRequest | Approval | Cancel | Call, Field(discriminator="type")]`; `emit.Emit = Callable[[str, dict], None]`; `emit.stdout_emit(name: str, payload: dict) -> None`; `emit.write_result(id: str, ok: bool, value=None, error: str | None = None) -> None`; `__main__.serve(stdin: asyncio.StreamReader, handlers: Handlers) -> Coroutine` where `Handlers` has `turn(req)`, `approval(msg)`, `cancel(msg)`, `call(msg) -> Any`.
- `TurnRequest` fields: `chat_id`, `persona` (dict: `id, name, tagline, system_prompt, tool_ids, skill_ids, mcp_server_ids, builtin, native_thinking, max_steps`), `provider` (`protocol, base_url, api_key, model`), `small_model: bool | None`, `workspace` (`id, name, root_path, instructions, is_chat`) or null, `knowledge_files: list[str]`, `skill_dirs: list[str]`, `skills: list[str]` (enabled names), `mcp_servers: list[dict]` (`id, name, command, args, env, enabled, auto_approve`), `settings: dict` (`searxng_url`, …), `lessons: list[str]`, `history: list[StoredRow]`. `StoredRow`: `role, content, tool_calls_json, tool_call_id, tool_name, model_message_json`.

- [ ] **Step 1:** `uv init --package --python 3.13 agent`, then in `agent/`: `uv add "pydantic-ai-slim[openai,mcp]==2.68.0" "pydantic-ai-harness[skills]==0.68.0" httpx pypdf` and `uv add --dev pytest pytest-asyncio ruff "pydantic-evals==2.68.0"`; set `[tool.pytest.ini_options] asyncio_mode = "auto"`.
- [ ] **Step 2: Write failing tests** in `test_protocol.py`:
  - `test_fixtures_round_trip`: for each fixture, `TypeAdapter(Incoming | Event | Result).validate_json(text).model_dump(mode="json") == json.loads(text)`.
  - `test_bad_line_is_ignored`: feed `serve` the lines `not json\n` then a `call` with method `ping`; assert one `result` line `{"type":"result","id":"1","ok":true,"value":"pong"}` and the error logged to stderr.
  - `test_unknown_method_returns_error`: `call` method `nope` → `result` with `ok:false`.
- [ ] **Step 3:** Run `cd agent && uv run pytest tests/test_protocol.py -v`. Expected: FAIL (import error).
- [ ] **Step 4:** Implement the models, `stdout_emit` (writes `{"type":"event","name","payload"}` + `\n` under a `threading.Lock`, flushes), and `serve` (each `turn` scheduled as a task; `call` answered via `write_result`; exceptions in a handler become `ok:false`). `python -m thea_agent` calls `serve` with the real handlers from Task 6 (a `ping` handler only, until then).
- [ ] **Step 5:** Run tests. Expected: PASS.
- [ ] **Step 6:** `justfile`: `setup` adds `uv sync --project agent --locked`; `test` adds `uv run --project agent pytest agent/tests`; `lint` adds `uv run --project agent ruff check agent`; `fmt` adds `uv run --project agent ruff format agent`. Run `just check`. Expected: PASS.
- [ ] **Step 7:** Commit `feat(agent): Python package, stdio protocol and server`.

### Task 2: STE checker and source ledger

**Files:**
- Create: `agent/src/thea_agent/tools/{__init__,ste,ste_words,ledger}.py`, `agent/tests/test_ste.py`, `agent/tests/test_ledger.py`
- Reference: `src-tauri/src/tools/ste.rs`, `src-tauri/src/tools/ledger.rs` (port logic and every `#[test]`)

**Interfaces:**
- Produces: `ste.check_text(text: str) -> list[Violation]`; tool `check_style(ctx: RunContext[TurnDeps], path: str) -> str` (starts `PASS` or `FAIL`); `ledger.add_source(ctx, ...)`, `list_sources(ctx) -> str`, `check_citations(ctx, path: str) -> str` (starts `PASS` / `FAIL`), with the same arguments as their `tools/mod.rs` schemas. Tools read the workspace root from `ctx.deps.root`. Tool-level failures raise `ToolFailed`; bad arguments that the model can fix raise `ModelRetry`.
- `TurnDeps` is defined here as a stub dataclass in `thea_agent/deps.py` (`root: Path | None`, `emit: Emit`, `chat_id: str`, `signals: Signals`) and extended in Task 6. `Signals`: `citations: tuple[bool, str] | None`, `style: tuple[bool, str] | None`.

- [ ] **Step 1:** Port each Rust test as a pytest test with the same name and values. Add `test_repo_docs_pass_ste_style` (walks `docs/` excluding `docs/dev/superpowers/`, asserts no violations), and `test_check_citations_records_signal` (after the call, `deps.signals.citations[0]` matches the `PASS` prefix).
- [ ] **Step 2:** Run `uv run pytest tests/test_ste.py tests/test_ledger.py -v`. Expected: FAIL.
- [ ] **Step 3:** Port the logic. `ste_words.py` holds the word lists from `ste.rs`.
- [ ] **Step 4:** Run tests. Expected: PASS.
- [ ] **Step 5:** Commit `feat(agent): STE checker and source ledger tools`.

### Task 3: Docket and research tools

**Files:**
- Create: `agent/src/thea_agent/tools/{docket,research}.py`, `agent/tests/test_docket.py`, `agent/tests/test_research.py`
- Reference: `src-tauri/src/tools/docket.rs`, `src-tauri/src/tools/research.rs` (port logic and tests)

**Interfaces:**
- Produces: `add_docket_item`, `update_docket_item`, `list_docket`, `export_calendar` (RFC 5545 `.ics`), `web_search(ctx, query: str)` (SearXNG at `ctx.deps.settings["searxng_url"]`), `fetch_url(ctx, url: str)` (SSRF guard: refuse loopback, private, link-local, unique-local and metadata addresses after DNS resolution, and on every redirect; PDF bodies via `pypdf`), `lookup_paper(ctx, ...)`. Mutating docket tools take `ctx` and call `approvals.require(ctx, "write", summary, details, diff)` (Task 5 defines it; until then create `thea_agent/approvals.py` with `require` as a no-op).
- `TurnDeps` gains `settings: dict` and `project_id: str`.

- [ ] **Step 1:** Port the Rust tests. Add `test_fetch_url_refuses_private_after_redirect` (an `httpx.MockTransport` that redirects to `http://127.0.0.1/` → `ToolFailed`), and `test_docket_json_is_read_only_to_file_tools` (deferred to Task 4's FileSystem config: here only assert `docket.READ_ONLY_PATHS == ("docket/docket.json",)` and `ledger.READ_ONLY_PATHS == ("research/sources.json",)`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Port the logic. Use `httpx.AsyncClient` with `follow_redirects=False` and a manual redirect loop that re-checks each hop.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat(agent): docket and research tools`.

### Task 4: Models, prompt, capabilities, toolsets

**Files:**
- Create: `agent/src/thea_agent/{models,prompt,capabilities,toolsets}.py`, `agent/src/thea_agent/how-you-work.md` (from `src-tauri/src/agent/how-you-work.md`, tool names updated per spec 4.3), `agent/tests/test_models.py`, `agent/tests/test_prompt.py`, `agent/tests/test_capabilities.py`, `agent/tests/test_toolsets.py`

**Interfaces:**
- `models.build_model(provider: dict) -> Model`: `OllamaModel(model, provider=OllamaProvider(base_url=<base>/v1))` for `protocol == "ollama"` (append `/v1` if missing), else `OpenAIChatModel(model, provider=OpenAIProvider(base_url, api_key or "none"))`.
- `models.Tier = Literal["small","medium","large"]`; `models.PromptBudget` dataclass with `for_tier(tier)` values from `agent/mod.rs:84-121`; `models.model_capabilities(provider) -> Capabilities(supports_tools, supports_thinking, context_length, params_b, tier)` from `/api/show` for Ollama (port `parse_show_response` and the tier tests from `providers/ollama.rs`), `Capabilities(True, False, None, None, "medium")` otherwise; `models.list_models(provider) -> list[dict]` (`/api/tags` or `/v1/models`, fields as `ModelInfo` in `providers/mod.rs`).
- `prompt.build_system_prompt(req: TurnRequest, tool_names: list[str], budget: PromptBudget) -> str`: as `build_system_prompt` in `agent/mod.rs:210`, minus the skills list and tool list (capabilities add those).
- `capabilities.TaskNudge` — registered as an output validator via `agent.output_validator`: `task_nudge(ctx: RunContext[TurnDeps], output: str) -> str` raises `ModelRetry(nudge)` when `nudge_for_reply(root, used_tools, output)` returns text and `ctx.retry < MAX_NUDGES`; `used_tools` = any `ToolCallPart` in `ctx.messages` of this run. Port `open_items`, `nudge_for`, `nudge_for_reply`, `EMPTY_REPLY_NUDGE` and their tests from `task.rs`.
- `capabilities.WrapUpNearRequestLimit(AbstractCapability)`: `before_model_request` enqueues `SystemPromptPart(WRAP_UP, scope="request")` when `requests_left(ctx) == 1`; `prepare_tools` returns `[]` then.
- `capabilities.ThoughtCap(PrepareTools)`: hides tools whose name ends with `sequentialthinking` once the run has `MAX_THOUGHTS` such calls.
- `capabilities.ToolErrors(AbstractCapability)`: `on_tool_execute_error` raises `ToolFailed(str(error))` for `OSError` and `httpx.HTTPError`, re-raises anything else.
- `toolsets.build(req: TurnRequest, deps: TurnDeps, caps: Capabilities, budget: PromptBudget, mcp_log: TextIO) -> TurnTools(capabilities: list, toolsets: list, tool_names: list[str])`:
  - no tools at all when `not caps.supports_tools`;
  - with a workspace root: `LocalWorkspace(root)`, `FileSystem(tools=("read_file","write_file","edit_file","list_directory","search_files","find_files"), read_only_patterns=(*FileSystem defaults, "research/sources.json", "docket/docket.json"))`, `Shell(tools=("run_command",))`;
  - `Skills(req.skill_dirs, include=req.skills, missing_directories="skip", workspace=LocalWorkspaceBackend(...))` per directory;
  - domain tools from Tasks 2–3 in a `FunctionToolset`, filtered by `persona.tool_ids` when non-empty;
  - one `MCPToolset(StdioTransport(command, args, env, log_file=mcp_log), tool_error_behavior="failed").prefixed(f"mcp__{slug(name)}")` per server from `mcp_servers_for` (port from `agent/mod.rs:185`); a server whose `__aenter__` / tool listing raises is skipped with a stderr line;
  - always `DetectLoops()`, `ToolOutputLimits(bands=[Band(over=budget.tool_output_chars, action=Truncate(max_chars=budget.tool_output_chars))])`, `WrapUpNearRequestLimit()`, `ThoughtCap(...)`, `ToolErrors()`.

- [ ] **Step 1: Failing tests:**
  - `test_models.py`: port the `/api/show` parse and tier tests; `test_build_model_appends_v1` (`base_url="http://localhost:11434"` → provider base URL ends `/v1`).
  - `test_prompt.py`: `test_prompt_has_persona_and_workspace`, `test_prompt_pins_knowledge_files_capped` (file content cut at `budget.knowledge_chars`), `test_prompt_lists_lessons_numbered`.
  - `test_capabilities.py` with `FunctionModel`: `test_task_nudge_retries_until_items_ticked` (TASK.md with one open item; the model's second reply follows the nudge; assert the nudge text reached the model), `test_task_nudge_gives_up_after_max_nudges` (run returns after `MAX_NUDGES` retries, no exception), `test_no_nudge_without_tool_use`, `test_wrap_up_on_last_request` (`request_limit=3`; third request has no tools and contains `WRAP_UP`), `test_thought_cap_hides_tool`, `test_oserror_becomes_failed_result` (tool raising `FileNotFoundError` → `ToolReturnPart.outcome == "failed"`, run continues).
  - `test_toolsets.py`: `test_sources_json_is_read_only` (model calls `write_file` on `research/sources.json` → not written), `test_failing_mcp_server_is_skipped` (command `false` → toolsets has no MCP entry, stderr line), `test_no_tools_when_model_cannot_call_tools`, `test_wired_framework_capabilities` (types `DetectLoops`, `ToolOutputLimits` present).
- [ ] **Step 2:** Run `uv run pytest tests/test_models.py tests/test_prompt.py tests/test_capabilities.py tests/test_toolsets.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat(agent): models, prompt and per-turn capabilities`.

### Task 5: Approvals

**Files:**
- Create: `agent/src/thea_agent/approvals.py`, `agent/tests/test_approvals.py`
- Modify: `agent/src/thea_agent/toolsets.py` (add `Permissions` + `HandleDeferredToolCalls`), `agent/src/thea_agent/__main__.py` (route `approval` lines)

**Interfaces:**
- `approvals.Approvals(emit: Emit)`: `allowed: set[tuple[str, str]]` (project_id, category) for the process lifetime; `async ask(chat_id, project_id, category, tool_name, summary, details, diff=None) -> bool` emits `agent:approval-request` with a fresh `request_id` and awaits it; `resolve(request_id: str, decision: str) -> bool`; `cancel_chat(chat_id)` cancels that chat's pending futures.
- `TurnDeps` gains `approvals: Approvals`.
- `approvals.require(ctx: RunContext[TurnDeps], category, summary, details, diff=None) -> None`: returns if `ctx.tool_call_approved` or `(project_id, category)` is allowed; (checked on `ctx.deps.approvals.allowed`) else raises `ApprovalRequired(metadata={"category", "summary", "details", "diff"})`.
- `approvals.handler(ctx, requests: DeferredToolRequests) -> DeferredToolResults`: for `Permissions`-held calls use `ask_permissions(requests, approver)`; for the rest read the call's metadata; ask in order; decision `always_allow_project` adds to `allowed`; `reject` → `ToolDenied`-style result from `requests.build_results`.
- In `toolsets.build`: `Permissions("read-only", remembered=<per-project set>)` and `HandleDeferredToolCalls(approvals.handler)`; MCP tools of servers without `auto_approve` get approval via the toolset's `process_tool_call` calling `require(ctx, "mcp", ...)`.

- [ ] **Step 1: Failing tests** (`FunctionModel` calling `write_file`, resolving through a fake emit):
  - `test_approve_runs_the_write`, `test_reject_tells_model_and_does_not_write` (`agent:tool-event` status `rejected`),
  - `test_always_allow_project_skips_next_ask` (second write in the same project emits no request; a different project does),
  - `test_docket_write_shows_diff` (`diff` field non-empty),
  - `test_cancel_while_pending` (Review Focus 1: `cancel_chat` → run raises `RunCancelled`, file not written, no further request).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5:** Commit `feat(agent): approvals through deferred tool calls`.

### Task 6: History, turn runner, reflection

**Files:**
- Create: `agent/src/thea_agent/{history,turn,reflection}.py`, `agent/tests/test_history.py`, `agent/tests/test_turn.py`, `agent/tests/test_reflection.py`
- Modify: `agent/src/thea_agent/__main__.py` (real `turn`, `cancel`, `call` handlers)

**Interfaces:**
- `history.to_model_messages(rows: list[StoredRow]) -> list[ModelMessage]`: rows with `model_message_json` via `ModelMessagesTypeAdapter`; rows without it become `UserPromptPart` / `TextPart` text only (tool rows rendered as `<tool_result name="...">…</tool_result>` user text); result passed through `repair_messages`.
- `history.message_event(chat_id, msg: ModelMessage) -> dict`: one `message` payload `{chat_id, role, content, tool_calls_json, tool_call_id, tool_name, model_message_json}`; a `ModelRequest` with several tool returns yields one payload per return (UI rows), the JSON on the first.
- `turn.run_turn(req: TurnRequest, emit: Emit, approvals: Approvals, token: CancellationToken) -> None`: up to `MAX_ROUNDS` runs of one `Agent(model, deps_type=TurnDeps, instructions=prompt, capabilities=..., toolsets=..., retries={"output": MAX_NUDGES})` via `agent.iter(..., usage_limits=UsageLimits(request_limit=budget.max_steps), cancellation_token=token)`; stream events → `chat:delta`, `agent:tool-event`, `message`; `agent:first-prompt` and `agent:prompt-size` before the first request; a round ends normally on output, or at the limit (`UsageLimitExceeded` caught, messages from the run kept); if open items remain and rounds are left, emit `agent:round` and start the next run from `round_brief(...)` only (text from `agent/mod.rs:1089`); emit `agent:incomplete` per `agent/mod.rs` rules; always emit `chat:finished` exactly once (error text on exception or `RunCancelled`).
- `reflection.detect_repeated_errors(messages) -> dict | None` (port from `agent/reflection.rs`, reading `ToolReturnPart.outcome in {"failed","retried"}`); `reflection.reflect(model, signal, transcript, lessons) -> str | None` with one `Agent(output_type=str)` and the prompt from `reflection.rs`; emitted as `lesson` `{persona_id, signal, text}`. `call` method `reflect_rating` runs it with `{"kind":"rating","up","comment"}`.
- `__main__` handlers: `turn` cancels any running task for that `chat_id` (and its pending approvals), starts a new one with a fresh token; `cancel` triggers the token; `call` methods `list_models`, `model_capabilities`, `test_provider`, `test_mcp_server` (connect and list tool names), `reflect_rating`.

- [ ] **Step 1: Failing tests:**
  - `test_history.py`: `test_round_trip_through_model_message_json` (run → message events → rows → `to_model_messages` equals the run's `all_messages()` after repair); `test_pre_migration_rows_replay_as_text` (Review Focus 3: rows with a tool call and no result → no `ToolCallPart` in output, provider accepts it via `FunctionModel` assertion).
  - `test_turn.py`: `test_one_finished_per_turn`, `test_round_rollover_at_step_cap` (`max_steps=2`, TASK.md open → `agent:round` with `round == 2`, second run's first request has only the brief), `test_incomplete_when_items_left`, `test_new_turn_cancels_running_turn` (Review Focus 4: two `turn` lines for one chat → first gets `chat:finished` with error, second completes), `test_tool_event_sequence` (`running` then `done` with the same `tool_call_id`).
  - `test_reflection.py`: port Rust tests; `test_lesson_only_on_signal`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `uv run pytest -v`. Expected: all PASS.
- [ ] **Step 5:** Manual: `echo '<turn fixture with provider ollama gemma4:e4b>' | uv run python -m thea_agent` prints `chat:delta` lines and one `chat:finished`.
- [ ] **Step 6:** Commit `feat(agent): turn runner, history and reflection`.

### Task 7: Rust sidecar and removal of the Rust agent

**Files:**
- Create: `src-tauri/src/sidecar.rs`
- Modify: `src-tauri/src/db.rs` (migration `ALTER TABLE messages ADD COLUMN model_message_json TEXT`; `StoredMessage.model_message_json: Option<String>`; `add_message` gains the argument), `src-tauri/src/lib.rs` (commands forward to the sidecar; `AppState { db, sidecar: Arc<Sidecar> }`), `src-tauri/Cargo.toml` (drop crates only the deleted code used: check `reqwest`, `futures-util`, `pdf-extract`, `similar`, `regex`, `ignore`, `which` with `cargo build` after deletion)
- Delete: `src-tauri/src/agent/`, `providers/`, `tools/`, `mcp.rs`, `approvals.rs`, `bin/eval.rs`

**Interfaces:**
- `Sidecar::spawn(app: AppHandle, db: Arc<Database>) -> Result<Arc<Sidecar>>`: debug builds run `uv run --project <repo>/agent python -m thea_agent`; release runs `<resource_dir>/python/bin/python3 -m thea_agent` (`python.exe` on Windows) with `PYTHONHOME` unset and `PYTHONNOUSERSITE=1`; stderr appended to `~/.thea/logs/agent.log`.
- `Sidecar::send_turn(&self, req: serde_json::Value)`, `send_approval(request_id, decision)`, `send_cancel(chat_id)`, `async call(method, params) -> Result<serde_json::Value>` (pending map keyed by uuid).
- Reader task: `event` → `message` → `db.add_message(...)`; `lesson` → `lessons::append_lesson(persona_id, Lesson { .. })` built from the payload's `signal` and `text`; anything else → `app.emit(name, payload)`; tracks running `chat_id`s from `turn` sent / `chat:finished` seen; on EOF emits `chat:finished {chat_id, error: "The agent process stopped."}` for each, fails pending calls, and marks itself dead so the next send respawns.
- `send_user_message` builds the `TurnRequest` JSON from the DB (everything `run_agent_turn_with_reflection` read: settings, chat, workspace, knowledge files, persona, skills dirs and enabled names from `skills::discover_skills`, MCP servers, lessons, stored rows) and calls `send_turn`.

- [ ] **Step 1: Failing Rust tests** in `sidecar.rs`:
  - `routes_message_events_to_db` and `relays_ui_events` (feed the reader lines through an in-memory pipe with a recording emitter),
  - `eof_finishes_running_chats` (Review Focus 2: after a `turn` for `c1` and EOF, one `chat:finished` for `c1` with an error),
  - `protocol_fixtures_deserialize` (reads `agent/tests/fixtures/protocol/*.json`).
- [ ] **Step 2:** Run `cargo test --manifest-path src-tauri/Cargo.toml sidecar`. Expected: FAIL.
- [ ] **Step 3:** Implement `sidecar.rs`, the migration, and the command rewiring; delete the old modules and their crates.
- [ ] **Step 4:** Run `just check`. Expected: PASS.
- [ ] **Step 5:** Manual: `just run`, send a research request on `gemma4:e4b`, approve one write, stop one turn mid-tool; then kill the Python process during a turn and confirm the error shows and the next send works.
- [ ] **Step 6:** Commit `feat!: run the agent in the Python sidecar`.

### Task 8: Evals in Python

**Files:**
- Create: `agent/src/thea_agent/eval.py`, `agent/tests/test_eval.py`
- Modify: `justfile` (`eval` recipe), `docs/dev/how-to/run-eval.md`
- Reference: `src-tauri/src/bin/eval.rs` (git history after Task 7)

**Interfaces:**
- `python -m thea_agent.eval --model gemma4:e4b --cases evals/research [--base-url http://localhost:11434]`: loads each case JSON (`id, prompt, min_sources=2, persona, seed_files`) into a `pydantic_evals.Dataset`; the task runs `run_turn` in a temp workspace with a recording emit and an approvals object that approves everything; evaluators compute `citations_pass`, `sources_ok`, `style_violations_per_100`, `sources`, `thought_steps` as `eval.rs` does; writes `evals/results/<suite>-<model>-<date>/<case>.json` and `<suite>-<model>-<date>.json`, with `results_stem` and `sanitize` ported.

- [ ] **Step 1: Failing tests:** port the `results_stem` / `sanitize` tests; `test_case_runs_with_function_model` (one case with a `FunctionModel` that writes a draft with one citation → result file written with the five fields).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement; `just eval` calls `uv run --project agent python -m thea_agent.eval --model {{model}} --cases {{cases}}`.
- [ ] **Step 4:** Run tests. Expected: PASS. Manual: `just eval gemma4:e4b evals/assistant` completes.
- [ ] **Step 5:** Commit `feat(agent): evals on pydantic-evals`.

### Task 9: Bundle Python into the installers

**Files:**
- Modify: `justfile` (new `bundle-agent triple` recipe; `build-macos`, `build-windows` depend on it), `src-tauri/tauri.conf.json` (`bundle.resources`: `"../agent/dist/python/": "python/"`), `.gitignore` (`agent/dist/`)

**Interfaces:**
- `just bundle-agent aarch64-apple-darwin` / `x86_64-pc-windows-msvc`: downloads the `python-build-standalone` CPython 3.13 `install_only` archive for the triple (pinned release tag and SHA-256 in the recipe), extracts to `agent/dist/python/`, then `uv export --project agent --no-dev --frozen > req.txt` and `uv pip install --python-platform <triple> --python-version 3.13 --only-binary :all: --target agent/dist/python/<site-packages> -r req.txt`, and installs `thea_agent` itself (`uv build --wheel` then the same `uv pip install`).

- [ ] **Step 1:** Add the recipe. Run `just bundle-agent aarch64-apple-darwin && agent/dist/python/bin/python3 -c "import thea_agent, pydantic_ai_harness"`. Expected: exit 0.
- [ ] **Step 2:** Run `just bundle-agent x86_64-pc-windows-msvc` and check `agent/dist/python/python.exe` and `Lib/site-packages/pydantic_core/*.pyd` exist. Expected: present.
- [ ] **Step 3:** `just build-macos`; open the `.dmg` app, send one message to Ollama. Expected: reply streams. `just build-windows` completes.
- [ ] **Step 4:** Commit `build: bundle the Python agent runtime into the installers`.

### Task 10: Docs, skills, ADR, changelog

**Files:**
- Create: `docs/dev/adr/0001-python-agent-sidecar.md` (Nygard: context, decision = approach A on pydantic-ai + harness, status Accepted, consequences incl. bundle size, harness 0.x pinning, Ollama context size)
- Modify: `docs/dev/explanation/architecture.md` (three parts: frontend, Rust app, Python agent; code map for `agent/src/thea_agent/`), `docs/how-to/connect-providers.md` (Ollama context size is set with `OLLAMA_CONTEXT_LENGTH` on the Ollama server), `docs/reference/tools-and-approvals.md` (tool names per spec 4.3), `skills/*.md` and any doc naming `list_dir`, `search`, `load_skill`, `edit_file` `target`/`replacement`, `docs/dev/how-to/run-eval.md`, `README.md` prerequisites (uv with install link), `CHANGELOG.md` (Unreleased: Changed, Removed)
- Modify: `src/components/SettingsModal.tsx` only if it shows the Ollama context-size setting — hide it for Ollama providers. (The one frontend change the spec's context-size decision implies; skip if the setting is not shown.)

- [ ] **Step 1:** `grep -rnE "\b(list_dir|load_skill|target|replacement)\b|\bsearch\b\(" skills docs agent/src` and update every hit.
- [ ] **Step 2:** Write the ADR and doc edits.
- [ ] **Step 3:** Run `just check` (includes `test_repo_docs_pass_ste_style`). Expected: PASS.
- [ ] **Step 4:** Commit `docs: Python agent architecture, ADR 0001, tool renames`.
