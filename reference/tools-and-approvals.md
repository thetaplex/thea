# Built-In Agent Tools and Approval Categories

It offers all of the tools that the active persona allows. A chat without a project has no persona. It uses its workspace folder in `~/.thea/chats/<chat-id>/` and gets only `web_search`, `fetch_url`, `read_file`, and `write_file`.

## Built-In Tools

| Tool | Approval Category | Required Arguments | Optional Arguments | Description and Limits |
|---|---|---|---|---|
| `list_directory` | Auto-allowed | None | `path` | Lists the entries of a folder inside the project. Returns up to 1000 entries. |
| `read_file` | Auto-allowed | `path` | `offset`, `limit` | Reads a text file inside the project with line numbers. `offset` is a zero-based line number. A call returns up to 2000 lines and is capped by the tier budget. A note at the end names the next line to read. Refuses `.env*` files. |
| `write_file` | `write` | `path`, `content` | None | Creates or overwrites a file inside the project, and makes any missing parent folders once you approve it. Shows a unified diff first. Refuses `research/sources.json` and `docket/docket.json`. |
| `edit_file` | `write` | `path`, `old_text`, `new_text` | None | Replaces `old_text` with `new_text` in `path`. `old_text` must occur once in the file. Shows a unified diff first. Refuses `research/sources.json` and `docket/docket.json`. |
| `search_files` | Auto-allowed | `pattern` | `path`, `include_glob` | Searches file contents with a regular expression. Returns lines as `file:line:text`, up to 1000 matches. Refuses `.env*` files. |
| `find_files` | Auto-allowed | `pattern` | `path` | Finds files by name with a glob pattern such as `**/*.md`. Returns up to 1000 matches. |
| `run_command` | `shell` | `command` | `timeout_seconds` | Runs a shell command in the project root. Needs approval on every call. Times out after 30 seconds by default and truncates output at 50000 characters. |
| `load_capability` | Auto-allowed | `name` | None | Returns the Markdown body of an active skill. |
| `web_search` | Auto-allowed | `query` | `max_results` | Searches `SearXNG`, then `Tavily` keyless, then `DuckDuckGo`. Accepts a string or up to 3 query strings. Caps results at 10. |
| `fetch_url` | Auto-allowed | `url` | `max_chars` | Fetches a public `http` or `https` page or `PDF` up to 5 MB. Default length is 6000 characters, capped at 20000 and the tier budget. |
| `lookup_paper` | Auto-allowed | One of `doi`, `title`, `arxiv_id` | None | Queries `OpenAlex`, `Crossref`, and `arXiv` for paper metadata and abstract. Title matches need a Jaccard similarity of at least `0.6`. |
| `add_source` | `write` | At least one of `doi`, `url`, `arxiv_id` | `title`, `relevance` | Resolves a source and appends it to `research/sources.json`. Uses `doi` first, then `arxiv_id`, then `url`. If the id does not resolve, it registers the `url`. Returns a key such as `[S1]`. Clamps `relevance` to `1..=5`. |
| `add_note` | `write` | `heading`, `note` | `path` | Adds one note as the last line under `## heading` in a Markdown file, `research/notes.md` by default. Makes the file and the heading if they do not exist. A heading matches only when it has the same text, ignoring `#`, case, and spacing. Shows a unified diff first. |
| `list_sources` | Auto-allowed | None | None | Lists all entries in `research/sources.json`, sorted by `relevance` from highest to lowest and then by key. |
| `check_citations` | Auto-allowed | `path` | None | Checks that every `[S#]` citation and `## References` item in `path` exists in `research/sources.json`. |
| `add_docket_item` | `write` | `title` | `kind`, `priority`, `due`, `project`, `notes` | Adds a task, event, decision, or note to `docket/docket.json` and renders `docket/DOCKET.md`. Returns a key such as `[D1]`. |
| `update_docket_item` | `write` | `key` | `status`, `priority`, `title`, `due`, `project`, `notes` | Updates an item in `docket/docket.json` and renders `docket/DOCKET.md`. |
| `list_docket` | Auto-allowed | None | `status`, `kind` | Lists items in `docket/docket.json`, sorted by status, priority, due date, and key. |
| `export_calendar` | `write` | `title`, `start` | `end`, `duration_minutes`, `location`, `description`, `reminder_minutes`, `slug` | Writes an `RFC 5545` `.ics` event file to `docket/calendar/<slug>.ics`. |

## Approval Categories

| Category | Tools | Session Auto-Approval |
|---|---|---|
| `write` | `write_file`, `edit_file`, `add_source`, `add_note`, `add_docket_item`, `update_docket_item`, `export_calendar` | Supports `Always Allow for Project` for the current app session. |
| `shell` | `run_command` | Never auto-approved. Every call asks for approval. |
| `mcp` | `mcp__<server>__<tool>` | Auto-approved when the server has `auto_approve: true` or after `Always Allow for Project`. |

In a chat without a project, `Always Allow for Project` applies only to that chat.
