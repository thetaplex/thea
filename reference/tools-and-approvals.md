# Built-In Agent Tools and Approval Categories

Without an active project, it offers only `load_skill`, `web_search`, `fetch_url`, and `lookup_paper`. With an active project, it offers all of the tools that the active persona allows.

## Built-In Tools

| Tool | Approval Category | Required Arguments | Optional Arguments | Description and Limits |
|---|---|---|---|---|
| `list_dir` | Auto-allowed | None | `path` | Lists up to 200 entries (depth 3) inside the project. Skips `.git`, `node_modules`, `target`, `.venv`, and `.env*`. |
| `read_file` | Auto-allowed | `path` | `start_line`, `end_line` | Reads a UTF-8 file up to 512 KB inside the project. Refuses `.env*` files. Line numbers start at 1. |
| `write_file` | `write` | `path`, `content` | None | Creates or overwrites a file inside the project. Shows a unified diff first. Refuses `research/sources.json`. |
| `edit_file` | `write` | `path`, `target`, `replacement` | None | Replaces the first match of `target` in `path`. Shows a unified diff first. Refuses `research/sources.json`. |
| `search` | Auto-allowed | `pattern` | None | Searches project files for a case-insensitive regular expression. Returns up to 100 matches. Skips `.env*`. |
| `run_command` | `shell` | `command` | None | Runs a shell command in the project root. Needs approval on every call. Times out at 60 seconds and truncates output at 16000 bytes. |
| `load_skill` | Auto-allowed | `name` | None | Returns the Markdown body of an active skill. |
| `web_search` | Auto-allowed | `query` | `max_results` | Searches `SearXNG`, then `Tavily` keyless, then `DuckDuckGo`. Accepts a string or up to 3 query strings. Caps results at 10. |
| `fetch_url` | Auto-allowed | `url` | `max_chars` | Fetches a public `http` or `https` page or `PDF` up to 5 MB. Default length is 6000 characters, capped at 20000 and the tier budget. |
| `lookup_paper` | Auto-allowed | One of `doi`, `title`, `arxiv_id` | None | Queries `OpenAlex`, `Crossref`, and `arXiv` for paper metadata and abstract. Title matches need a Jaccard similarity of at least `0.6`. |
| `add_source` | `write` | One of `doi`, `url`, `arxiv_id` | `title`, `relevance`, `note` | Resolves a source and appends it to `research/sources.json`. Returns a key such as `[S1]`. Clamps `relevance` to `1..=5`. |
| `list_sources` | Auto-allowed | None | None | Lists all entries in `research/sources.json`, sorted by `relevance` from highest to lowest and then by key. |
| `check_style` | Auto-allowed | `path` | None | Checks a Markdown file against measurable `ASD-STE100` rules and returns `PASS` or a line-by-line violation list. |
| `check_citations` | Auto-allowed | `path` | None | Checks that every `[S#]` citation and `## References` item in `path` exists in `research/sources.json`. |

## Approval Categories

| Category | Tools | Session Auto-Approval |
|---|---|---|
| `write` | `write_file`, `edit_file`, `add_source` | Supports `Always Allow for Project` for the current app session. |
| `shell` | `run_command` | Never auto-approved. Every call asks for approval. |
| `mcp` | `mcp__<server>__<tool>` | Auto-approved when the server has `auto_approve: true` or after `Always Allow for Project`. |
