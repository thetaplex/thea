# Storage Layout, Files, and Settings

By default, it stores the global state in `~/.thea/`. Set the `THEA_HOME` environment variable to use another directory. When `THEA_HOME` is not empty, it uses a mock keychain in memory instead of the keychain of the operating system.

## Global Files (`~/.thea/`)

| Path | Format | Contents |
|---|---|---|
| `~/.thea/thea.sqlite3` | SQLite (`WAL`) | Tables: `projects`, `project_knowledge`, `chats`, `messages`, `settings`, `skill_states`, `personas`, `mcp_servers`. |
| `~/.thea/settings.json` | JSON | Mirror of `AppSettings` with `API` keys removed. |
| `~/.thea/providers.json` | JSON | List of `ProviderEntry` records with `API` keys removed. |
| `~/.thea/skills.json` | JSON | Global custom skills (`SkillInfo` array). |
| `~/.thea/mcp.json` | JSON | Configured `stdio` `MCP` servers (`McpServerConfig` array). |
| `~/.thea/lessons/<persona-id>.md` | Markdown | Up to 20 `Reflexion` lessons for `<persona-id>`, oldest dropped first. |

## Project Workspace Files (`<project>/`)

| Path | Written By | Contents |
|---|---|---|
| `<project>/TASK.md` | `write_file`, `edit_file` | Checklist of `- [ ]` and `- [x]` items that controls when a turn is complete. |
| `<project>/.thea/skills.json` | UI / `create_skill` | Project-scoped custom skills. |
| `<project>/research/sources.json` | `add_source` only | Research ledger (`Source` array with keys `S1`, `S2`, ...). Protected from `write_file` and `edit_file`. |
| `<project>/research/notes.md` | `write_file`, `edit_file` | Running factual notes tagged with `[S#]` keys. |
| `<project>/research/outline.md` | `write_file`, `edit_file` | Section outline mapping `[S#]` learning lines to sections. |
| `<project>/research/drafts/*.md` | `write_file`, `edit_file` | Paper, proposal, and essay drafts checked by `check_style` and `check_citations`. |
| `<project>/research/book/` | `write_file`, `edit_file` | Book research corpus (`brief.md`, `open-questions.md`, `chapters/`, `timeline.md`, `people.md`, `places.md`, `terms.md`). |

## Settings (`AppSettings`)

| Field | Type | Default | Description |
|---|---|---|---|
| `default_provider` | `string` | `"ollama"` | Active provider ID. |
| `default_model` | `string` | `""` | Active model ID. |
| `default_persona_id` | `string` | `""` | Fallback persona ID when a chat or project does not name one (resolves to `research-assistant`). |
| `ollama_base_url` | `string` | `"http://127.0.0.1:11434"` | Endpoint URL for `Ollama`. |
| `openai_base_url` | `string` | `"http://127.0.0.1:1234/v1"` | Endpoint URL for the `custom` `OpenAI` provider. |
| `context_tokens` | `u64` | `32768` | Context window sent as `num_ctx` to `Ollama` (floored at `2048` and capped at the model maximum). |
| `searxng_url` | `string` | `"http://127.0.0.1:8888"` | Local `SearXNG` URL for `web_search`. Empty string skips `SearXNG`. |
| `windows_shell` | `string` | `"pwsh"` | Shell for `run_command` on Windows: `"pwsh"`, `"powershell"`, `"cmd"`, or `"git-bash"`. |
| `mac_shell` | `string` | `"zsh"` | Shell for `run_command` on macOS and Linux: `"zsh"`, `"bash"`, or `"sh"`. |
| `auto_approve_reads` | `bool` | `true` | Auto-approve read-only workspace tools. |
| `small_model` | `bool \| null` | `null` | Optional override to force `Small` (`true`) or `Large` (`false`) tier budgets. |
| `disabled_builtin_skills` | `string[]` | `[]` | Names of built-in skills that the user turned off. |
| `seeded_mcp_presets` | `string[]` | `[]` | IDs of `MCP` presets already seeded (`sequential-thinking`, `playwright`). |
