# Research Assistant: tool-enforced research pipeline

Date: 2026-11-13. Status: draft for approval, builder-checked.

## Intent

Make Thea's Research Assistant persona work like a real researcher on a small local model (target `gemma4:e4b` via Ollama): frame a question, find and read sources, keep notes, and write a research paper or proposal whose every citation resolves to a real, fetched source. The agent should also improve over time from its own outcomes.

Why: today the persona is a four-line prompt with only workspace file tools. It cannot search, cannot read a web page or PDF, and nothing stops it inventing references. The literature shows 11% to 57% of LLM-generated citations are fabricated and that models cannot reliably judge their own citations, so correctness has to come from tools, not prompting.

## Goals

- A research run produces a Markdown paper or proposal in the project where every citation maps to a source record that was resolved against an external database or fetched from a live URL.
- Works acceptably with a 4B model: short prompts, tool results sized for a small context window, state kept in files rather than chat history.
- The agent learns from outcomes: lessons from citation checks and user ratings are stored and replayed in later sessions, with the user able to see and edit them.
- Quality is measured by an eval that runs locally, not asserted.

## Non-goals

- Multi-agent orchestration (planner, writer, critic as separate agents). Revisit once the eval exists to compare against.
- Fine-tuning or any weight updates.
- A full reference manager or BibTeX export. Markdown bibliography only, for now.
- The Personal Assistant persona (files, mail, calendar, Docket) described in `Thea.pdf`. Sibling persona, separate design.
- Javascript-heavy or login-walled sites. Covered by the optional Playwright MCP server, not by the built-in fetcher.

## Anti-goals

- A paper that reads well but cites a source the agent never retrieved. This is the failure the whole design exists to prevent; a polished hallucination is worse than a rough honest draft.
- Lessons memory that silently drifts the agent's behaviour without the user seeing it.
- Sending workspace contents to the web. Search queries carry only what the model writes into them; fetch sends URLs only.

## Constraints

- Rust backend (Tauri 2), React frontend; new tools are Rust, same shape as the existing `tools/` module and approval gate.
- No API keys required for the default path. Keyed providers may be optional extras.
- Keep the existing XML fallback for models without native tool calling.
- Reflexion needs a feedback signal. Where no signal exists, no lesson is written.
- Existing repo conventions: pnpm, Biome, clippy clean, `just check` green, Conventional Commits.

## Approaches considered

1. **Prompt and skills only.** Rewrite the persona, add method skills, let the model keep a lessons file through `write_file`. No web access and nothing enforces citations. Rejected: cannot meet the no-hallucination goal.
2. **Tool-enforced pipeline.** New tools for search, fetch, scholarly lookup, a source ledger that is the only route into a bibliography, and a citation checker. Skills encode the method. Reflexion-style lessons with real signals. **Chosen.** The model does the reading and writing; tools decide what counts as a source.
3. **Multi-agent roles.** Closer to commercial deep-research products. Rejected for now: four roles on a 4B model is slow, and the critic role is exactly the unreliable self-judge the literature warns about. Non-goal until measurable.

## Design

### 1. Tools (Rust, `src-tauri/src/tools/research.rs`)

All read-only tools are auto-approved, as `read_file` is today. Writes go through the existing approval gate.

| Tool | Args | Returns | Notes |
|---|---|---|---|
| `web_search` | `query`, optional `max_results` (default 5, cap 10) | numbered list of `title`, `url`, `snippet` | DuckDuckGo HTML endpoint, no key. Provider is a small trait so Brave or Tavily can be added with a key later. |
| `fetch_url` | `url`, optional `max_chars` (default 6000, cap 20000) | `title`, `url`, `fetched_at`, extracted text | HTML to readable text (strip nav, scripts, boilerplate). PDF to text. Truncated with a marker. Rejects non-http(s), private and loopback addresses. |
| `lookup_paper` | `doi` or `title` (one required) | canonical record: `title`, `authors`, `year`, `venue`, `doi`, `url`, `abstract` (truncated) | OpenAlex first, Crossref fallback, arXiv for `arxiv:` ids. Returns `not_found` rather than a guess. |
| `add_source` | one of `doi`, `url`, or `arxiv_id`; optional `note` | source key like `[S3]` and the resolved record | The only way into the bibliography. Resolves through `lookup_paper` or `fetch_url` internally; refuses if neither resolves. Appends to `research/sources.json` in the project. |
| `list_sources` | none | the ledger, compact | Lets the model re-read what it may cite without re-fetching. |
| `check_style` | `path` of a Markdown draft | report: per-sentence violations of the measurable ASD-STE100 rules (sentence over 20 words in procedures or 25 in descriptions, paragraph over 6 sentences, passive voice by auxiliary-plus-participle heuristic, contractions, semicolons, noun cluster over 3 words, words from the unapproved list with their approved alternative) and a pass/fail | Pure function. Headings, code blocks, references and quoted text are skipped. The unapproved-word list ships as a compiled-in table of the most common entries (about 300 pairs), not the full dictionary. |
| `check_citations` | `path` of a Markdown draft | report: each `[Sn]` found, whether it exists in the ledger, orphan sources, and a pass/fail | Pure function over the draft and ledger. Also exposed to the eval. |

`web_search` and `fetch_url` are the generic pair; `lookup_paper` and the ledger are what make scholarly output trustworthy.

**Scoping (builder's call).** Tools are per persona. `Persona` gains a `tool_ids` list with the same semantics as `mcp_server_ids`: empty means all built-in tools. The Research Assistant seeds with the workspace tools plus the six research tools; other personas keep only the workspace tools, so their tool schemas (and the XML fallback prompt) do not grow. No persona-editor UI for this field yet; it is seed data and JSON.

`write_file` and `edit_file` refuse paths under `research/sources.json` so the ledger stays tool-only. `add_source` uses the existing `write` approval category.

### 2. Source ledger and research folder

Per project, under `research/`:

- `sources.json`: array of resolved records with keys `S1`, `S2`, ... Written only by `add_source`.
- `notes.md`: the model's running notes, one entry per source or finding, each tagged with its source key. Written through the normal `write_file` / `edit_file` tools, so the user approves and sees them.
- `drafts/`: paper and proposal drafts.

The citation convention is `[S3]` inline and a `## References` section generated from the ledger. `check_citations` fails a draft that cites a key not in the ledger or has a References entry not in the ledger.

### 3. Skills (bundled, in `~/.thea/skills.json` defaults)

Four skills, loaded on demand through the existing `load_skill` tool, each under 400 words so a 4B model can hold one plus its working set:

- `research-method`: frame the question, decide what evidence would settle it, search broad then narrow, prefer primary sources, stop criteria.
- `source-triage`: judge a result before fetching (domain, date, author, type), when to `lookup_paper` versus `fetch_url`, how to record a note with a source key.
- `write-research-paper`: structure (abstract, background, method, findings, limitations, references), draft from `notes.md` only, every claim gets a `[Sn]`, run `check_citations` before declaring done, fix or remove unverifiable claims.
- `write-research-proposal`: problem, prior work, aims, method, timeline, risks; same citation rules.
- `write-ste`: ASD-STE100 Simplified Technical English as the house style for everything the persona writes: one topic per paragraph, one instruction per sentence, 20 words in procedures and 25 in descriptions, active voice, approved verb forms only (no complex tenses, no `-ing` verbs), no contractions or semicolons, the same word for the same thing throughout, simple words over complex ones. Run `check_style` before `check_citations`; fix every violation it reports. The skill carries the rules and a short table of common unapproved words; the tool carries the long list.
- `think-in-steps`: how to use the `sequentialthinking` tool (section 6): plan in at most 5 numbered thoughts before the first search, one more thought after each batch of sources to decide what is still missing, keep each thought under 60 words, set `nextThoughtNeeded` to false once a plan exists. Integers for `thoughtNumber` and `totalThoughts`.

Note on scope: ASD-STE100 was written for maintenance documentation. Applied to research writing it trades some nuance for clarity and checkability, which is the point here: a 4B model follows short mechanical rules far better than "write clearly", and a checker can verify them.

The persona prompt names the skills and the rule: "You may only cite keys returned by `add_source`. If you cannot find a source, say so."

### 4. Persona prompt and small-model fixes

- Rewrite the Research Assistant system prompt in clean English, under 200 words, with the citation rule, the notes-first habit, and the stop condition (run `check_citations`, report pass).
- Replace the model-name heuristic for tool support with Ollama's per-model `capabilities` from `/api/show`, cached per model for the session. Keep the heuristic for OpenAI-compatible providers.
- Context budget: file tree capped at 30 entries and knowledge-file snippets at 2000 characters when the model is in a small-model tier (parameter size under 8B as reported by Ollama, or user override in settings). Tool results above the cap are truncated with a marker and a hint to use `read_file` with a range.
- Thinking: **native model thinking is turned off** for the Research Assistant (`think: false` on Ollama requests) and replaced by the `sequentialthinking` MCP tool, see section 6. Hidden thinking tokens are invisible, uncapped, and leave nothing behind for reflection. Tool-based thoughts are visible in the chat, capped by the skill, persisted as tool messages, and become the trajectory summary that the reflection step reads. Cost: each thought is one extra round trip through the agent loop, so `max_agent_steps` for the persona rises from 15 to 30 and thought steps are shown collapsed in the UI. Other personas keep native thinking.
- Context window (decided with the user, 2026-11-13): Thea currently never sets `num_ctx`, so Ollama falls back to its default (4096 on current releases) and silently truncates from the front, dropping the system prompt that carries the citation rule. Add a `context_tokens` setting, default 32768, sent as `options.num_ctx` on every Ollama request. Clamp it to the model's `context_length` from `/api/show` (131072 for gemma4:e4b) and show both numbers in Settings with a note that larger values cost RAM and slow every step. We rejected defaulting to the model maximum: Ollama reserves the KV cache for the whole `num_ctx` up front, which costs several extra gigabytes per chat on a 16 GB machine, prompt processing is linear in tokens re-sent each step, and small models lose precision at the far end of long contexts. State lives in `research/` files, so the context does not need to be large. The budgets above assume 32k. The eval reports the longest prompt it sent so the budget can be checked against the setting.

### 5. Self-improvement (Reflexion with real signals)

Per persona, `~/.thea/lessons/<persona-id>.md`, plain Markdown the user can open from the Skills pane.

Signals, in order of trust:

1. `check_citations` result at the end of a research run (pass, or the list of failures).
2. User rating on the final assistant message: thumbs up or down, optional one-line comment.
3. Tool errors repeated within one run (same tool, same error class, 3 or more times).

When a signal fires, the agent makes one extra model call with the trajectory summary and the signal, asking for a single lesson of at most two sentences in the form "When X, do Y." The lesson is appended with date and signal. Lessons are injected into the system prompt on later sessions for that persona.

Guardrails, from the memory-governance literature:

- Cap of 20 lessons, first in first out. No usage tracking (builder's call; revisit if good lessons get evicted in practice).
- Each lesson shows in the UI with its source signal; the user can delete or edit any line.
- No lesson is written without a signal. Pure self-evaluation is not a signal.
- Lessons are per persona, never shared across personas.

### 5b. Delivering bundled content to existing installs (builder's call)

Everything today is seed-once and user-editable, so new defaults would reach only fresh installs. Rules:

- **Built-in personas** are not user-editable (only custom personas have save and delete), so their rows are re-seeded from `default_personas()` on every launch. The rewritten Research Assistant prompt and `tool_ids` arrive this way.
- **Built-in skills** are compiled in with `include_dir!`, the same mechanism templates use, and reported with `source: "builtin"`. They can be toggled but not edited or deleted; a project or global skill with the same name overrides them, matching the existing project-over-global rule. Skills pane shows the source.
- **MCP presets** are added to `mcp.json` on launch only when no entry with that id exists, disabled. Deleting one stays deleted.

### 6. Optional MCP servers

Two presets in `mcp.json`, both via `npx`:

- **`sequential-thinking`** (`@modelcontextprotocol/server-sequential-thinking`): enabled, and listed in the Research Assistant's `mcp_server_ids`. The server is a pure scaffold: it records each thought and echoes back the count, nothing else. Its value is making the model's planning explicit and steerable. Two small code changes make it usable: `McpServerConfig` gains an `auto_approve` flag (true for this preset) so thoughts do not hit the approval gate on every call, and the agent coerces tool arguments to the schema's declared types before dispatch, because small models send `"1"` where the schema wants `1` and this server rejects that.
- **`playwright`**: disabled. Covers sites the built-in fetcher cannot render. No further code.

Both require Node on the user's machine; the Settings pane says so when the preset is enabled and `npx` is missing.

### 7. Eval ("measured, not claimed")

`just eval` runs `src-tauri/src/bin/eval.rs` against a local Ollama model:

- Five fixed research prompts with known answerable sources, in `evals/research/*.json`.
- For each: run the agent headless, then score with `check_citations` (hard fail on any unverified citation), `check_style` (violations per 100 sentences), count of resolved sources, number of thought steps, and whether a draft was produced within the step limit.
- Prints a table per model and writes `evals/results/<model>-<date>.json`. Not in CI by default (needs a running model); a CI job may run it on a self-hosted runner later.

## Left to the builder

- HTML readability extraction approach (a crate versus hand-rolled tag stripping).
- Exact DuckDuckGo HTML parsing and the user-agent string.
- Where the thumbs rating lives in the chat UI and its event name.
- How `check_citations` parses `[Sn]` versus code blocks that happen to contain brackets.
- Ordering of implementation phases, as long as the ledger and `check_citations` land before the writing skills.
- Decoupling `run_agent_turn` from `AppHandle` for the headless eval (an event-sink and approval-policy seam).

## Open risks

- DuckDuckGo may rate-limit or change its HTML. The provider trait exists for that reason.
- OpenAlex and Crossref are public but can be slow; tools time out at 15 seconds and return an error the model can act on.
- A 4B model may still paraphrase a source wrongly even when the citation resolves. The eval measures citation validity, not claim faithfulness; that is a later metric.
