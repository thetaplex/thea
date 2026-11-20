# Built-In Model Providers and Personas

## Built-In Model Providers

It seeds 6 of the providers in `~/.thea/providers.json`. It stores `API` keys in `~/.thea/credentials`, in a section named after the provider ID, such as `[openrouter]`.

| ID | Name | Protocol | Default Base URL |
|---|---|---|---|
| `ollama` | Ollama | `ollama` | `http://127.0.0.1:11434` |
| `openrouter` | OpenRouter | `openai` | `https://openrouter.ai/api/v1` |
| `openai` | OpenAI | `openai` | `https://api.openai.com/v1` |
| `groq` | Groq | `openai` | `https://api.groq.com/openai/v1` |
| `lmstudio` | LM Studio | `openai` | `http://127.0.0.1:1234/v1` |
| `custom` | Custom (OpenAI-Compatible) | `openai` | `http://127.0.0.1:1234/v1` |

## Chats Without a Project

A persona belongs to a project. A chat without a project has no persona, no skills, no `MCP` servers, and no lessons.

It does not use `TASK.md`. Its tools are `web_search`, `fetch_url`, `read_file`, and `write_file`. The model can save a summary of the chat to the folder of the chat with `write_file`. The greeting changes with the time of day: "Good morning! What's on your mind?"

## Built-In Personas

Thea refreshes the 2 built-in personas in SQLite on every launch.

Each built-in persona uses only the built-in skills in this table. Both personas can use all of your own skills.

| Skill | Personal Assistant | Research Assistant |
|---|---|---|
| `manage-docket`, `draft-communication`, `weekly-review` | Yes | No |
| `source-triage`, `write-brief`, `write-report` | Yes | Yes |
| `book-research`, `deep-research`, `research-method`, `write-book-chapter`, `write-essay`, `write-research-paper`, `write-research-proposal` | No | Yes |

A persona keeps the old tool IDs (`list_dir`, `search`, and `load_skill`) in storage. Thea maps them to the new tools. The table shows the new names.

| ID | Name | Native Thinking | Linked `MCP` Servers | Allowed Built-In Tools |
|---|---|---|---|---|
| `personal-assistant` | Personal Assistant | `false` | `sequential-thinking`, `playwright` | `list_directory`, `read_file`, `write_file`, `edit_file`, `search_files`, `find_files`, `run_command`, `load_capability`, `web_search`, `fetch_url`, `lookup_paper`, `add_source`, `list_sources`, `add_note`, `check_citations`, `add_docket_item`, `update_docket_item`, `list_docket`, `export_calendar` |
| `research-assistant` | Research Assistant | `false` | `sequential-thinking` | `list_directory`, `read_file`, `write_file`, `edit_file`, `search_files`, `find_files`, `load_capability`, `web_search`, `fetch_url`, `lookup_paper`, `add_source`, `list_sources`, `add_note`, `check_citations` |
