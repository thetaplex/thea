# Personal Assistant: tool-enforced docket, calendar export, and drafting pipeline

Date: 2026-11-15. Status: approved and implemented.

## Intent

Make Thea's Personal Assistant persona work with the same tool-enforced depth as the Research Assistant on a small local model (target `gemma4:e4b` via Ollama): capture tasks, events, decisions, and notes in a workspace Docket (`docket/docket.json` + auto-rendered `docket/DOCKET.md`), export RFC 5545 `.ics` calendar files for events and reminders, search and read the web for everyday lookups, draft clear messages, memos, agendas, and meeting notes checked by `check_style`, and learn from outcomes via Reflexion lessons.

Why: previously the Personal Assistant persona had a short generic prompt and only basic workspace file and shell tools. Without a structured ledger for tasks and events, models overwrite or lose items when editing Markdown checklists directly, invent `[D#]` item references in weekly reviews, or produce invalid calendar files. Putting the Docket and `.ics` generation behind dedicated tools gives small models a reliable, verifiable workflow.

## Goals

- Every task, event, decision, or note is recorded through `add_docket_item` and updated through `update_docket_item` in `docket/docket.json`, with `docket/DOCKET.md` rendered automatically so the user can inspect it in the Files or Artifacts pane.
- Events and reminders export to standards-compliant RFC 5545 `.ics` files (`docket/calendar/<slug>.ics`) via `export_calendar` so the user can open them in Apple Calendar, Outlook, or Google Calendar with one click.
- Drafted communications (`docket/drafts/<slug>.md`) and action plans (`docket/plans/<slug>.md`) pass `check_style` (`ASD-STE100`) and reference valid `[D#]` keys.
- The agent learns from `check_style` outcomes, user ratings, and repeated tool errors via per-persona Reflexion lessons (`~/.thea/lessons/personal-assistant.md`).
- Quality is measured by a headless evaluation suite (`evals/assistant/*.json`) through the existing `eval` binary.

## Non-goals

- Direct OAuth or CalDAV/IMAP synchronization with Google Workspace, Microsoft 365, or Apple iCloud. Calendar integration uses local `.ics` file export; email and memo composition writes Markdown drafts in `docket/drafts/`.
- Academic paper lookup (`lookup_paper`) or academic bibliography enforcement (`add_source`, `check_citations`). Those remain scoped to the Research Assistant.
- Background daemon notifications or OS-level alarm daemons outside the user's calendar app.

## Constraints

- Rust backend (Tauri 2), React frontend; all new tools live in `src-tauri/src/tools/docket.rs` and wire into the existing tool registry and approval gate.
- `write_file` and `edit_file` must refuse `docket/docket.json` (just as they refuse `research/sources.json`) so the model cannot corrupt the JSON ledger or forge keys.
- Bundled skills must stay under 400 words each with `Use when` in the frontmatter description.
- All user and developer documentation under `docs/` (outside `docs/dev/superpowers/`) must pass the `repo_docs_pass_ste_style` test (`ASD-STE100`).

## Design

### 1. Tools (`src-tauri/src/tools/docket.rs`)

Read-only tools (`list_docket`) are auto-approved. Mutating tools (`add_docket_item`, `update_docket_item`, `export_calendar`) use the `write` approval category and show a unified diff before writing.

| Tool | Approval | Args | Returns | Notes |
|---|---|---|---|---|
| `add_docket_item` | `write` | `title` (required), optional `kind` (`task`, `event`, `decision`, `note`), `priority` (`1..=5`), `due` (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM`), `project`, `notes` | Assigned key (`[D1]`, `[D2]`, ...) and summary | Appends to `docket/docket.json` and re-renders `docket/DOCKET.md`. |
| `update_docket_item` | `write` | `key` (required, e.g. `D1` or `[D1]`), optional `status` (`open`, `done`, `canceled`), `priority`, `title`, `due`, `project`, `notes` | Updated `[D#]` summary | Updates the matching item in `docket/docket.json` and re-renders `docket/DOCKET.md`. |
| `list_docket` | Auto-allowed | optional `status` (`open`, `done`, `canceled`, `all`), `kind` | Compact sorted list of matching `[D#]` items | Sorted by status (`open` first), priority (`5` down to `1`), due date, and key number. |
| `export_calendar` | `write` | `title`, `start` (`YYYY-MM-DD` or `YYYY-MM-DD HH:MM`), optional `end`, `duration_minutes` (default `60`), `location`, `description`, `reminder_minutes` (default `15`), `slug` | Relative path `docket/calendar/<slug>.ics` and summary | Generates RFC 5545 `VCALENDAR` / `VEVENT` / `VALARM` and writes `docket/calendar/<slug>.ics`. |

### 2. Docket storage and protection

Per project, under `docket/`:

- `docket/docket.json`: canonical array of `DocketItem` records with sequential keys `D1`, `D2`, ... Written only by `add_docket_item` and `update_docket_item`. Both `write_file` and `edit_file` check `docket::is_docket_file` and refuse direct edits.
- `docket/DOCKET.md`: human-readable Markdown view grouped into `## Open` and `## Completed & Canceled`, regenerated automatically on every `save_docket`.
- `docket/calendar/<slug>.ics`: RFC 5545 calendar files written by `export_calendar`.
- `docket/drafts/<slug>.md`: emails, memos, and agendas referencing `[D#]` keys.
- `docket/plans/<slug>.md`: daily or weekly action plans referencing `[D#]` keys.

### 3. Bundled skills (`skills/`)

Three new skills compiled in via `include_dir!`, each under 400 words:

- `manage-docket`: triage an inbox dump, meeting notes, or action list into `docket/docket.json` with `add_docket_item` and `update_docket_item`, score priority `1..=5`, and export dated events with `export_calendar`.
- `draft-communication`: draft emails, memos, agendas, and status updates in `docket/drafts/<slug>.md`, ground action items in `[D#]` keys, and verify prose with `check_style`.
- `weekly-review`: inspect the docket with `list_docket`, update completed or stale items, write an action plan in `docket/plans/<slug>.md` (`Top Priorities`, `Schedule`, `Open Tasks`, `Decisions and Notes`), and run `check_style`.

### 4. Persona configuration and Reflexion signal

- `personal-assistant` in `src-tauri/src/db.rs` sets `native_thinking: false`, `mcp_server_ids: vec!["sequential-thinking"]`, and `tool_ids`: `list_dir`, `read_file`, `write_file`, `edit_file`, `search`, `run_command`, `load_skill`, `web_search`, `fetch_url`, `check_style`, `add_docket_item`, `update_docket_item`, `list_docket`, and `export_calendar`.
- `src-tauri/src/agent/reflection.rs` adds `Signal::Style { pass, detail }` (`check_style_pass` / `check_style_fail`). When a turn runs `check_style` without `check_citations` (the Personal Assistant path), the agent records a Reflexion lesson from the style outcome.

### 5. Evaluation (`evals/assistant/*.json` and `src-tauri/src/bin/eval.rs`)

Each case may set an optional `persona` (default `research-assistant`) and `seed_files`. For `personal-assistant`, the `eval` binary scores every Markdown file in `docket/drafts/` and `docket/plans/`: `citations_pass` means every `[D#]` reference resolves to an item in `docket/docket.json`, `sources` counts Docket items, and `min_sources` is the minimum Docket item count. `evals/research/*.json` cases are unchanged.

- `evals/assistant/weekly-triage.json`: triages a seeded `inbox.md` into the Docket (`>= 3` items), exports the kickoff meeting `.ics`, and writes `docket/plans/weekly-plan.md`.
- `evals/assistant/schedule-kickoff.json`: logs an architecture review event and a preparation task (`>= 2` items), exports the `.ics` invite, and drafts `docket/drafts/arch-review-invite.md`.
- `evals/assistant/status-memo.json`: reads seeded `notes.md`, logs the open task and decision (`>= 2` items), and writes `docket/drafts/status-memo.md` that passes `check_style`.
