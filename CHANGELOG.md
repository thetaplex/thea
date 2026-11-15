# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Streaming chat against Ollama and OpenAI-compatible endpoints, with native and fallback tool calling.
- Projects with bundled templates, project instructions and pinned knowledge files.
- Workspace tools (`list_dir`, `read_file`, `search`, `write_file`, `edit_file`, `run_command`) behind an approval gate.
- Artifacts pane with live HTML preview, Skills pane, and stdio MCP server support.
- Provider API keys stored in the OS keychain.
- Research Assistant persona for sourced papers and proposals.
- Tool `web_search` to search the web through a local SearXNG instance, with Tavily keyless and then DuckDuckGo as fallbacks.
- `just searxng` starts SearXNG in Docker with the JSON API enabled; `searxng_url` setting.
- Tool `fetch_url` to fetch web pages and PDFs.
- Tool `lookup_paper` to look up papers.
- Tool `add_source` to record a source in the research ledger file in the project. It is the only route into a bibliography.
- Tool `list_sources` to list the recorded sources.
- Tool `check_citations` to find unsupported citations in a draft.
- Tool `check_style` to measure ASD-STE100 rules in a draft.
- Ten bundled skills: task checklist, deep research (decompose, breadth, depth, gap check, outline), book research (intake questions, one chapter per session, a corpus the author writes from), research method, source triage, research paper, research proposal, essay, STE writing and step-by-step thinking.
- `TASK.md` checklist: the agent keeps working while it has open items, up to four nudges per turn.
- Rounds: when the step cap hits with `TASK.md` still open, the turn continues in a fresh context (up to 6 rounds) with a brief built from the request, the last status and `TASK.md`; notes and the ledger carry the knowledge over.
- Source relevance: `add_source` takes a 1 to 5 score against the question; `list_sources` returns the most relevant first; the triage skill collects wide and reads the top.
- MCP preset `sequential-thinking`, enabled and auto-approved.
- MCP preset `playwright`, disabled.
- Auto-approve option for MCP servers.
- Collapsed thought steps in chat.
- Lessons for each persona, kept in the lessons folder in your home directory. Thea learns from citation checks, thumbs ratings and repeated tool errors.
- Editing of lessons in the Skills pane.
- Personas can choose their own tools, native thinking and maximum steps.
- Setting `context_tokens` for the context window (default 32768, limited to the model maximum).
- Model tiers (small under 8B, medium under 20B, large) set prompt sizes, tool output caps, the step cap (30/45/60) and the research targets (3-5, 5-8, 8-12 sources), stated to the model in a Budget section.
- Headless research eval with five cases (`just eval`). Results go to the eval results folder.
- Repository documentation under `docs/` (`tutorials/`, `how-to/`, `reference/`, `explanation/`) following Diataxis and `ASD-STE100`.

### Changed

- Proprietary license; the repository is no longer open source.
- Built-in skills no longer appear in the Skills pane.
- Developer documentation moved to `docs/dev/`.
- Built-in personas refresh on every launch.
- `read_file` accepts line ranges.
- Ollama model capabilities come from the model itself.
- Native thinking is off for the Research Assistant.
- Prompts and tool output now fit a small-model budget.
- Tool arguments from models are converted to the expected type.

### Fixed

- Saving settings no longer touches the OS keychain when no legacy key exists.

[Unreleased]: https://github.com/thetaplex/thea/commits/HEAD
