# Storage Layout, Files, and Settings

By default, it stores the global state in `~/.thea/`. Set the `THEA_HOME` environment variable to use another directory. The `API` keys are in the `credentials` file in that directory.

## Global Files (`~/.thea/`)

| Path | Format | Contents |
|---|---|---|
| `~/.thea/thea.sqlite3` | SQLite (`WAL`) | Tables: `projects`, `project_knowledge`, `chats`, `messages`, `settings`, `skill_states`, `personas`, `mcp_servers`. |
| `~/.thea/credentials` | INI | `API` keys, one `[provider-id]` section each with an `api_key = ...` line, like `~/.aws/credentials`. Mode `600` on macOS and Linux. You can edit it by hand. Thea changes only `api_key` lines and keeps comments and other lines. |
| `~/.thea/settings.json` | JSON | Mirror of `AppSettings` with `API` keys removed. |
| `~/.thea/providers.json` | JSON | List of `ProviderEntry` records with `API` keys removed. |
| `~/.thea/skills.json` | JSON | Global custom skills (`SkillInfo` array). |
| `~/.thea/mcp.json` | JSON | Configured `stdio` `MCP` servers (`McpServerConfig` array). |
| `~/.thea/lessons/<persona-id>.md` | Markdown | Up to 20 `Reflexion` lessons for `<persona-id>`, oldest dropped first. |
| `~/.thea/chats/<chat-id>/` | Folder | Workspace for a chat without a project. It has the same layout as a project workspace. Thea deletes it when you delete the chat. |

## Project Workspace Files (`<project>/`)

| Path | Written By | Contents |
|---|---|---|
| `<project>/TASK.md` | `write_file`, `edit_file` | Checklist of `- [ ]` and `- [x]` items that controls when a turn is complete. |
| `<project>/.thea/skills.json` | UI / `create_skill` | Project-scoped custom skills. |
| `<project>/research/sources.json` | `add_source` only | Research ledger (`Source` array with keys `S1`, `S2`, ...). Protected from `write_file` and `edit_file`. |
| `<project>/research/notes.md` | `write_file`, `edit_file` | Running factual notes tagged with `[S#]` keys. |
| `<project>/research/outline.md` | `write_file`, `edit_file` | Section outline mapping `[S#]` learning lines to sections. |
| `<project>/research/drafts/*.md` | `write_file`, `edit_file` | Paper, proposal, and essay drafts checked by `check_citations`. |
| `<project>/research/book/` | `write_file`, `edit_file` | Book research corpus (`brief.md`, `open-questions.md`, `chapters/`, `timeline.md`, `people.md`, `places.md`, `terms.md`). |
| `<project>/docket/docket.json` | `add_docket_item`, `update_docket_item` | Personal Assistant docket (`DocketItem` array with keys `D1`, `D2`, ...). Protected from `write_file` and `edit_file`. |
| `<project>/docket/DOCKET.md` | `add_docket_item`, `update_docket_item` | Rendered Markdown view of open and completed docket items. |
| `<project>/docket/calendar/*.ics` | `export_calendar` | `RFC 5545` calendar event files with `VALARM` reminders. |
| `<project>/docket/drafts/*.md` | `write_file`, `edit_file` | Emails, memos, and agendas that cite `[D#]` keys. |
| `<project>/docket/plans/*.md` | `write_file`, `edit_file` | Action plans that cite `[D#]` keys. |
| `<project>/drafts/*.md` | `write_file`, `edit_file` | Drafted messages, memos, agendas, and meeting notes. |

## Settings (`AppSettings`)

| Field | Type | Default | Description |
|---|---|---|---|
| `default_provider` | `string` | `"ollama"` | Active provider ID. |
| `default_model` | `string` | `""` | Active model ID. |
| `default_persona_id` | `string` | `""` | The persona of a project that does not name one (resolves to `research-assistant`). A chat without a project has no persona. |
| `ollama_base_url` | `string` | `"http://127.0.0.1:11434"` | Endpoint URL for `Ollama`. |
| `openai_base_url` | `string` | `"http://127.0.0.1:1234/v1"` | Endpoint URL for the `custom` `OpenAI` provider. |
| `context_tokens` | `u64` | `32768` | Stored, but not used. The window size of `Ollama` comes from `OLLAMA_CONTEXT_LENGTH` on the server. |
| `searxng_url` | `string` | `"http://127.0.0.1:8888"` | Local `SearXNG` URL for `web_search`. Empty string skips `SearXNG`. |
| `windows_shell` | `string` | `"pwsh"` | Shell for `run_command` on Windows: `"pwsh"`, `"powershell"`, `"cmd"`, or `"git-bash"`. |
| `mac_shell` | `string` | `"zsh"` | Shell for `run_command` on macOS and Linux: `"zsh"`, `"bash"`, or `"sh"`. |
| `auto_approve_reads` | `bool` | `true` | Auto-approve read-only workspace tools. |
| `small_model` | `bool \| null` | `null` | Optional override to force `Small` (`true`) or `Large` (`false`) tier budgets. |
| `disabled_builtin_skills` | `string[]` | `[]` | Names of built-in skills that the user turned off. |
| `seeded_mcp_presets` | `string[]` | `[]` | IDs of `MCP` presets already seeded (`sequential-thinking`, `playwright`). |
