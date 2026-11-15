# Thea Documentation

Thea is a chat app for your desktop, like `ChatGPT`. It also runs as an agent over your own project folder. You pick a persona: Personal Assistant, Research Assistant, or Software Engineer. The agent reads and edits files, runs commands, searches the web, and keeps a ledger of sources. It works with local models through `Ollama` or any server that speaks the `OpenAI` protocol, and with hosted providers such as `OpenRouter`. Every write and command waits for your approval.

## Personas

Thea ships with 3 personas. Each one has its own system prompt, tool set, and starter prompts. You can add your own.

| Persona | Use it for | Tools |
|---|---|---|
| Personal Assistant | Plans, drafts, notes, everyday tasks | Files, `run_command`, skills |
| Research Assistant | Sourced briefs, papers, proposals, essays, book research | Files, `web_search`, `fetch_url`, `lookup_paper`, source ledger, style and citation checks |
| Software Engineer | Reading code, writing tests, fixing bugs, scaffolding | Files, `run_command`, skills |

## Main Features

- **Agent loop for small models**: a `TASK.md` checklist, up to 4 nudges in a round, and up to 6 rounds. Model tiers (small, medium, large) set the prompt budget, the cap on tool output, and the step cap.
- **Approval gate**: `list_dir`, `read_file`, and `search` run inside the project without asking. `write_file`, `edit_file`, `add_source`, and `run_command` show a diff or a command and wait for Approve, Always Allow for Project, or Reject. The tools for files stay inside the project root and do not read `.env*` files.
- **Research with a source ledger**: `web_search` uses local `SearXNG`, then `Tavily` in keyless mode, then `DuckDuckGo`. `fetch_url` reads pages and `PDF` files. `lookup_paper` queries `OpenAlex`, `Crossref`, and `arXiv`. A draft can cite only keys that `add_source` returned. `check_citations` and `check_style` (`ASD-STE100`) run before the agent completes a draft.
- **Projects and templates**: open a folder or start from 5 templates (`React + Vite`, `Python`, `Node.js CLI`, `static HTML`, empty). Add project instructions and pin files into the prompt.
- **Artifacts and live preview**: view code, read Markdown, and run `HTML` and `SVG` in a sandboxed `iframe`.
- **Skills and lessons**: 10 bundled skills loaded on demand with `load_skill`. Thea records up to 20 lessons for each persona in `~/.thea/lessons/`. The lessons come from citation checks, ratings, and repeated tool errors.
- **Model Context Protocol (`MCP`)**: connect `stdio` `MCP` servers. `sequential-thinking` and `playwright` ship as presets.
- **Any model can use tools**: Thea uses the native tool calls of a model when the provider reports them. For other models, it parses `<tool_call>` blocks.
- **Secrets in the keychain**: provider `API` keys live in the macOS Keychain or Windows Credential Manager, not in `~/.thea/*.json`.

## Download

Installers for macOS and Windows are on the [Releases](https://github.com/thetaplex/thea/releases) page. The builds have no code signature, so `macOS Gatekeeper` and `Windows SmartScreen` show a warning on the first launch.

This documentation follows the [Diataxis](https://diataxis.fr/) system and Simplified Technical English (`ASD-STE100`). Each file is for 1 topic.

## Tutorials

Start here if you are new to Thea. A tutorial takes you through a full workflow step by step.

- [Tutorial 1: Build and Preview Your First Project](tutorials/first-project.md)
- [Tutorial 2: Write a Sourced Research Brief](tutorials/research-brief.md)

## How-To Guides

Use these guides when you want to do a specific task. Each guide gives the steps for 1 goal.

- [Connect an `OpenAI` Provider](how-to/connect-providers.md)
- [Run a Local Search Engine with `SearXNG`](how-to/local-search-searxng.md)
- [Pin Project Files and Set Instructions](how-to/project-context.md)
- [Create and Manage Custom Skills](how-to/custom-skills.md)
- [Create a Custom Persona](how-to/custom-personas.md)
- [Connect a `stdio` `MCP` Server](how-to/mcp-servers.md)
- [Rate Answers and Edit Persona Lessons](how-to/persona-lessons.md)

## Reference

Use the reference when you need exact names, parameters, limits, or file paths.

- [Providers and Personas](reference/providers-and-personas.md)
- [Agent Tools and Approval Categories](reference/tools-and-approvals.md)
- [Bundled Skills and Project Templates](reference/skills-and-templates.md)
- [Model Tiers and Prompt Budgets](reference/tiers-and-budgets.md)
- [Storage Layout, Database, and Settings](reference/storage-and-settings.md)

## Explanation

Read the explanation to learn about the design of Thea and why it uses these rules.

- [The Agent Loop, `TASK.md`, and Rounds](explanation/agent-loop-and-rounds.md)
- [Tool-Enforced Research and the Source Ledger](explanation/source-ledger.md)
- [Thinking Modes and Context Window Sizing](explanation/thinking-and-context.md)
- [Self-Improvement with `Reflexion` Lessons](explanation/reflexion-lessons.md)
- [Security Boundaries and Known Limits](explanation/security-model.md)
