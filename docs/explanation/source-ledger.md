# Tool-Enforced Research and the Source Ledger

This guide explains how the ledger of sources stops a model from inventing citations.

A model can invent citations or guess paper titles from memory. Prompt instructions alone do not stop a model from making up references. Thea enforces the integrity of citations through tools, not through instructions.

1. **Single path into the ledger**: `research/sources.json` holds every record for a source in a project. Only the `add_source` tool can write to `research/sources.json`. Both `write_file` and `edit_file` check `is_ledger_file` and refuse any path that resolves to `research/sources.json`.
2. **Verification on registration**: when the model calls `add_source` with `doi` or `arxiv_id`, it checks `OpenAlex`, `Crossref`, or `arXiv`. When the model calls `add_source` with a `url`, it fetches the page with `fetch_url`. If a site answers with `HTTP` `4xx` or `5xx` and the model passes `title`, it registers the entry as `not fetched`. If the domain does not resolve at all, `add_source` refuses the source.
3. **Mechanical citation check**: before finishing a draft, the model runs `check_citations`. This tool scans the draft outside of code blocks for every `[S#]` marker and every item under `## References`. It fails if any cited key is missing from `research/sources.json`.
