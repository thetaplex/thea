# Built-In Model Providers and Personas

## Built-In Model Providers

It seeds 6 of the providers in `~/.thea/providers.json`. It stores `API` keys in the keychain of the operating system under the service name `app.thetaplex.thea`.

| ID | Name | Protocol | Default Base URL |
|---|---|---|---|
| `ollama` | Ollama | `ollama` | `http://127.0.0.1:11434` |
| `openrouter` | OpenRouter | `openai` | `https://openrouter.ai/api/v1` |
| `openai` | OpenAI | `openai` | `https://api.openai.com/v1` |
| `groq` | Groq | `openai` | `https://api.groq.com/openai/v1` |
| `lmstudio` | LM Studio | `openai` | `http://127.0.0.1:1234/v1` |
| `custom` | Custom (OpenAI-Compatible) | `openai` | `http://127.0.0.1:1234/v1` |

## Built-In Personas

Thea refreshes the 3 built-in personas in SQLite on every launch.

| ID | Name | Native Thinking | Linked `MCP` Servers | Allowed Built-In Tools |
|---|---|---|---|---|
| `personal-assistant` | Personal Assistant | `true` | None | `list_dir`, `read_file`, `write_file`, `edit_file`, `search`, `run_command`, `load_skill` |
| `research-assistant` | Research Assistant | `false` | `sequential-thinking` | `list_dir`, `read_file`, `write_file`, `edit_file`, `search`, `load_skill`, `web_search`, `fetch_url`, `lookup_paper`, `add_source`, `list_sources`, `check_style`, `check_citations` |
| `software-engineer` | Software Engineer | `true` | None | `list_dir`, `read_file`, `write_file`, `edit_file`, `search`, `run_command`, `load_skill` |
