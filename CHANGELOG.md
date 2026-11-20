# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-11-20

### Changed

- Provider `API` keys are now in `~/.thea/credentials`, a file like `~/.aws/credentials` that only your user account can read, instead of the operating system keychain. Thea no longer asks for your keychain password. Keys saved in the keychain by earlier builds are not moved: enter them again in Settings. See [ADR 0003](https://github.com/thetaplex/thea/blob/main/docs/dev/adr/0003-credentials-file.md).
- App icon from the ThetaPlex icon family (thetaplex/www ADR 0003), on every platform.
- Thea's source code is now open source under the Apache License 2.0, in this repository. The user docs moved to `docs/`.

### Security

- Updated Tauri to 2.12.7, `rusqlite` to 0.43, and other dependencies.
- The CI workflow token is read-only.

## [0.3.0] - 2026-11-19

### Changed

- Saving Settings with **LM Studio** selected starts LM Studio's server on the port in the provider URL when it isn't running. This needs LM Studio's `lms` tool. If the server can't start, Settings stays open and shows why.
- The **Model** list in Settings fills in for the selected provider, and updates as you change its URL or API key. You no longer need to select **Test Connection** first.

### Fixed

- **Test Connection** for OpenRouter now checks the API key. OpenRouter lists its models without a key, so the test passed while every chat failed with `401 Missing Authentication header`.
- Settings won't save while a key marked **(Required)** is empty. Closing Settings with an unsaved API key shows a warning instead of discarding the key.

## [0.2.0] - 2026-11-19

### Added

- The artifact bar has a **Refresh** button. It reads the open file again from the project folder and reloads the preview.
- The artifact bar has a **Save as PDF** button. It opens the artifact in its own window with the print dialog. On macOS, select **PDF** > **Save as PDF**. On Windows, select **Microsoft Print to PDF**.

### Changed

- New projects for the Personal Assistant and the Research Assistant offer only **Empty Project** and **Existing Folder**. The code templates are for custom personas only. Tutorial 1 starts from an empty project, and it installs Thea from a release instead of building it from source.

### Fixed

- When Thea asks you a question in a project, it waits for your answer. Before, it could guess the answers and go on, for example with the intake questions of a new book. A new tool, `ask_user`, ends the turn after the question.
- When you open a different project, the chat pane and the artifact pane show only that project. Before, the old project's artifacts, streaming state and errors could stay on screen, and a slow project load could replace a later one.

## [0.1.2] - 2026-11-18

Thea is in beta. The installers have no code signature from Apple or Microsoft. To open Thea the first time, see [Install Thea](https://github.com/thetaplex/thea/blob/main/how-to/install-thea.md).

### Added

- How-to guide [Install Thea](https://github.com/thetaplex/thea/blob/main/how-to/install-thea.md): how to open Thea the first time on macOS and on Windows.

### Fixed

- The macOS app opens after you download it. Versions 0.1.0 and 0.1.1 had no signature for the bundle as a whole, so macOS said "Thea is damaged and can't be opened". The app now has an ad-hoc signature, and macOS shows the usual warning with **Open Anyway**. `just build-macos` now fails if the signature does not pass `codesign --verify`.

## [0.1.1] - 2026-11-18

### Fixed

- Workflow prototype: a written part that has headings is sent back to the model once. If the last try still has headings, code keeps only the text before the first one. The model had written a whole paper as the Abstract, so every heading was in the file twice and the word count stopped at the first `## References`.

## [0.1.0] - 2026-11-18

### Added

- Streaming chat against Ollama and OpenAI-compatible endpoints, with native tool calling.
- Projects with bundled templates, project instructions and pinned knowledge files.
- Workspace tools (`list_directory`, `read_file`, `search_files`, `find_files`, `write_file`, `edit_file`, `run_command`) behind an approval gate.
- Artifacts pane with live HTML preview, Skills pane, and stdio MCP server support.
- Provider API keys stored in the OS keychain.
- Research Assistant persona for sourced papers and proposals.
- Tool `web_search` to search the web through a local SearXNG instance, with Tavily keyless and then DuckDuckGo as fallbacks.
- `just searxng` starts SearXNG in Docker with the JSON API enabled; `searxng_url` setting.
- Tool `fetch_url` to fetch web pages and PDFs.
- Tool `lookup_paper` to look up papers.
- Tool `add_source` to record a source in the research ledger file in the project. It is the only route into a bibliography.
- Tool `list_sources` to list the recorded sources.
- Tool `add_note` to add one note under a heading of a notes file, such as `research/notes.md`. The Research Assistant and the Personal Assistant have it. The research skills use it instead of `edit_file`, which made the model delete the heading it added under.
- `add_note` refuses a note that cites a key `add_source` did not return. Drafts copy keys from the notes, so a made-up key in a note became a made-up citation.
- Tool `check_citations` to find unsupported citations in a draft.
- Workflow prototype behind `THEA_WORKFLOW=1` for the Research Assistant: code runs the steps and the model fills in the text. Code searches for each question and reads the results in order until two give facts. The model lists the facts on each page, and code registers the source and writes the notes. Before, the model ran research as a tool loop: it did one search, took notes from the search snippets, and almost never read a page.
- Workflow prototype: the planner writes a search query for each question, and code searches with it. The question text made a bad query: it is long and often does not name its subject. If research finds no facts at all, the workflow writes no document and says why, instead of drafting from the model's memory with no sources.
- Bundled skills: deep research (decompose, breadth, depth, gap check, outline), book research (intake questions, one chapter per session, a corpus the author writes from), research method, source triage, research paper, research proposal, and essay.
- `TASK.md` checklist: the agent keeps working while it has open items, up to four nudges per turn.
- Rounds: when the step cap hits with `TASK.md` still open, the turn continues in a fresh context (up to 6 rounds) with a brief built from the request, the last status and `TASK.md`; notes and the ledger carry the knowledge over.
- Source relevance: `add_source` takes a 1 to 5 score against the question; `list_sources` returns the most relevant first; the triage skill collects wide and reads the top.
- MCP preset `sequential-thinking`, enabled and auto-approved.
- MCP preset `playwright` (pinned `@playwright/mcp@0.0.85`), enabled and linked to the Personal Assistant for pages that need a browser.
- Auto-approve option for MCP servers.
- Collapsed thought steps in chat.
- Lessons for each persona, kept in the lessons folder in your home directory. Thea learns from citation checks, thumbs ratings and repeated tool errors.
- Editing of lessons in the Skills pane.
- Personas can choose their own tools, native thinking and maximum steps.
- Model tiers (small under 8B, medium under 20B, large) set prompt sizes, tool output caps, the step cap (30/45/60) and the research targets (3-5, 5-8, 8-12 sources), stated to the model in a Budget section.
- Headless research eval with five cases (`just eval`). Results go to the eval results folder.
- Personal Assistant docket: tools `add_docket_item`, `update_docket_item` and `list_docket` keep tasks, events, decisions and notes in `docket/docket.json` with `[D#]` keys, and render `docket/DOCKET.md`.
- Tool `export_calendar` to write RFC 5545 `.ics` files to `docket/calendar/`.
- Skills manage docket, draft communication and weekly review.
- Assistant eval cases in `evals/assistant/`.
- A chat without a project has its own workspace folder in `~/.thea/chats/` and uses all the tools of its persona.
- Repository documentation under `docs/` (`tutorials/`, `how-to/`, `reference/`, `explanation/`) following Diataxis and `ASD-STE100`.

### Changed

- A chat without a project has only `web_search`, `fetch_url`, `read_file`, and `write_file`. It uses no `TASK.md`, and its greeting changes with the time of day.
- In a project, the first tool call writes `TASK.md`. A text reply ends the turn only when `TASK.md` has no open items, or when the next item asks the user a question. A reply before `TASK.md` exists gets 1 nudge. A finished `TASK.md` is emptied when the next turn starts.
- The agent runs in a Python sidecar on pydantic-ai and pydantic-ai-harness. The Rust app starts it and relays its events. The installers bundle a CPython 3.13 runtime. Building needs `uv`.
- Tools have new names: `list_dir` is `list_directory`, `search` is `search_files` and `find_files`, and `load_skill` is `load_capability`. `edit_file` takes `old_text` and `new_text`. `read_file` takes `offset` and `limit` in place of line ranges. Skills follow these names.
- `add_source` accepts an id together with its `url`. It uses the id first and registers the `url` if the id does not resolve.
- The `write-research-paper` and `write-report` templates have one TODO line per finding. The rule to keep a shared Findings TODO line is gone, because it made a second copy of a TODO line.
- Repeated tool calls get a nudge from the harness `DetectLoops` capability in place of a refusal. The step cap is a request limit with a wrap-up request.
- Set the context size of Ollama with `OLLAMA_CONTEXT_LENGTH` on the Ollama server. The settings dialog no longer shows `context_tokens`.
- `promptfoo` runs the eval (`just eval [model] [suite]`) in place of the Rust `eval` binary. The checks look at what the user gets: the turn ends without an error and with no open items, the file exists with no `TODO` line and the right length, the drafts cite enough sources, the last reply is true, and the calendar event is correct.
- Proprietary license; the repository is no longer open source.
- Built-in skills no longer appear in the Skills pane.
- Developer documentation moved to `docs/dev/`.
- Built-in personas refresh on every launch.
- Ollama model capabilities come from the model itself.
- Native thinking is off for the Research Assistant.
- Planning and the `TASK.md` checklist are part of the core prompt for every persona. The model plans only when the request needs tools. The `task-checklist` and `think-in-steps` skills are gone.
- Native thinking is off for the Personal Assistant. It uses web search and sequential thinking.
- `just build` and `just release` build the Windows installer on macOS with `cargo-xwin`. The Windows Actions workflow is gone.
- Prompts and tool output now fit a small-model budget.
- Tool arguments from models are converted to the expected type.

### Removed

- The persona of a chat. A persona belongs to a project, and a chat without a project is a plain chat. The persona selector in the sidebar is gone, and **New persona** is in the project dialog.
- `eval_personas.json`. The evaluation reads the personas from the database of the app.
- The `note` argument of `add_source`. Notes go to `research/notes.md`.
- The text `<tool_call>` fallback for models without native tool calling. These models chat without tools.
- The per-model Ollama context size (`num_ctx`).
- Software Engineer persona. Thea deletes it from existing databases on launch.

### Fixed

- Token caps reach Ollama models. pydantic-ai sent the cap as `max_completion_tokens`, which Ollama ignores, so a reply stuck in a loop ran until the turn timed out.
- `just eval` sends the app's `searxng_url` with each turn, as the app does. It sent no settings, so evals never used SearXNG and failed once Tavily's keyless daily limit was used up.

- The section lengths of the writing skills add up to the length of the document. Before, a brief whose every section kept its range had fewer than 500 of its 500 to 700 words.
- The eval checks the file and the calendar event of each case. Before, `promptfoo` dropped them from the case, and the `deliverable` and `event` checks passed without a look.
- A persona with native thinking off now stops an Ollama model from thinking. Before, the setting did not get to Ollama, and the model used its default.
- Saving settings no longer touches the OS keychain when no legacy key exists.
- A thinking call past the limit of 5 no longer ends the turn. The tool stays available and answers that the thinking steps are used up.
- `edit_file` needs `old_text`. A call without it is told to use `write_file` to change the whole file.

[Unreleased]: https://github.com/thetaplex/thea/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/thetaplex/thea/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/thetaplex/thea/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/thetaplex/thea/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/thetaplex/thea/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/thetaplex/thea/releases/tag/v0.1.0
