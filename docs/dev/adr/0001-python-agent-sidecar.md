# 1. Run the Agent in a Python Sidecar

Date: 2026-11-16

## Status

Accepted. [ADR 0002](0002-promptfoo-evals.md) changes it: `promptfoo` runs the evaluations.

## Context

Thea had its agent in Rust. It held the agent loop, the provider clients, the tools, the approvals, and the `MCP` client. Most of this code does a job that the `pydantic-ai` framework and `pydantic-ai-harness` already do. Examples are tool errors, retries, loop detection, output caps, approvals, file tools, shell, skills, and `MCP`.

We had three options:

- **A. A sidecar process over `stdio`.** The Rust app starts a Python process. The two exchange `JSON` lines.
- **B. A local `HTTP` server.** The UI would talk to it with server-sent events. A local port needs a token. The history of chats would live in two places. The `IPC` layer would change.
- **C. Python embedded in Rust with `PyO3`.** Async bridging, the `GIL`, and the Windows cross-build cost more than the port.

Two limits shape the choice. The Windows installer is cross-built on macOS with `cargo-xwin`, so a tool such as `PyInstaller` cannot build it. And the `OllamaModel` of `pydantic-ai` uses the `OpenAI`-compatible `/v1` endpoint of `Ollama`. That endpoint cannot set the context size (`num_ctx`).

## Decision

We use option A. The agent is a Python package in `agent/`, built on `pydantic-ai` and `pydantic-ai-harness`. The Rust app keeps `SQLite`, settings, projects, chats, skill discovery, lesson storage, and the file pane. It starts the agent as a sidecar and relays its events to the UI.

The UI events do not change. Python never opens `SQLite`. The sidecar has no network port.

We bundle a `python-build-standalone` `CPython 3.13` runtime and the locked dependencies in the installers. The `just bundle-agent` recipe builds it for each target.

We write our own code only where the framework has no feature: the research, ledger, docket, and `ASD-STE100` tools, the `TASK.md` rounds, reflection, and the `stdio` bridge. Tool names follow the harness.

We pin `pydantic-ai-slim`, `pydantic-ai-harness`, and `pydantic-evals` to exact versions.

## Consequences

- The Rust agent code is gone. The framework now does the work of many guards that we wrote by hand. Repeated-call refusal is now the `DetectLoops` nudge. The step cap is a request limit with a wrap-up request.
- The installers are larger. The bundled runtime and its dependencies take about 230 MB unpacked on macOS, before compression.
- `pydantic-ai-harness` is a `0.x` library, so its `API` can change between minor versions. We pin exact versions and upgrade on purpose, with the test suite and the evaluation as the check.
- Some tools have new names: `list_dir` is now `list_directory`, `search` is now `search_files` and `find_files`, and `load_skill` is now `load_capability`. `edit_file` takes `old_text` and `new_text`. Skills and the system prompt follow these names.
- Models that cannot call tools natively no longer get a text `<tool_call>` fallback.
- Thea cannot set the context size of `Ollama`. Users set `OLLAMA_CONTEXT_LENGTH` on the `Ollama` server. The `context_tokens` setting stays in storage but has no effect, and the settings dialog hides it.
- If the agent crashes, the app keeps running. Rust starts the agent again.
- A developer needs `uv` to build, test, and run the agent.
