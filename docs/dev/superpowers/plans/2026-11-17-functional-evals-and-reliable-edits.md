# Functional Evals, Code-Owned Checklist, and Edits Without Exact Text

**Goal:** the app does what the user asked, and the evals check that from the user's side.

**Order:** A, then B, then C. A comes first, so that each later change is judged by checks that match what a user sees. A run after A will fail more cases than today. That is the point: it shows the real failures.

**Branch:** `feat/pydantic-ai-agent`. Uncommitted work stays as it is.

## Global Constraints

- Fix causes, not symptoms. No higher retry limits, no guesses that can edit the wrong text.
- Rust only reads and writes the database. No agent behavior in Rust tests.
- Plain chats (no project) are not changed by this plan.
- uv for Python, `just check` green after each part.
- Docs follow ASD-STE100 (`test_repo_docs_pass_ste_style`).

---

## Part A: Eval checks based on what the user gets

Today, report-sqlite-wal passes with all `TASK.md` items open, 53 style issues, and a reply that says the fixes are done. A user would not accept that.

**Files:** `agent/src/thea_agent/eval.py`, `evals/promptfoo/score.py`, `evals/promptfoo/provider.py`, `evals/research/*.json`, `evals/assistant/*.json`, `agent/tests/test_eval.py`, `docs/dev/how-to/run-eval.md`, `docs/dev/reference/cli-and-ste-rules.md`.

| Check | Passes when | Data it reads |
|---|---|---|
| `no_error` (keep) | the turn ended without an error | `chat:finished.error` |
| `complete` (new) | no `agent:incomplete` event | the events of the turn: works before and after Part B |
| `deliverable` (new) | a draft matches the case's `deliverable.glob`, has no `TODO` line, and its word count is in `deliverable.words` | case field, the draft files |
| `citations` (keep) | every key resolves | as today |
| `sources` (change) | the number of distinct keys **cited** in the drafts is at least `min_sources` | the drafts, not the ledger size |
| `style` (gate) | the last `check_style` result of the turn is `PASS` | the tool rows of the turn |
| `honest_report` (new) | the final reply names the draft path, and if the last `check_style` or `check_citations` result is `FAIL`, the reply says `FAIL` | final reply, tool rows |
| `event` (new, assistant) | the exported `.ics` has the case's `event.start`, `event.end`, and `event.location` | case field, `docket/calendar/*.ics` |

- [ ] Case fields: `deliverable: {glob, words: [min, max]}` and `event: {start, end, location}`. Word ranges come from the skills: brief 500 to 700, report 2000 to 4000, proposal 1500 to 2500, short paper 1500 to 2500, essay 800 to 1200.
- [ ] `Outcome` keeps the events, the paths of the drafts, and the `.ics` text.
- [ ] `metrics()` returns the new fields; `score.py` turns each one into a check.
- [ ] Tests: one for each check, pass and fail, with stub runs as in `test_eval.py`.
- [ ] Run both suites once and record the baseline in `evals/results/promptfoo/`.

## Part B: Code owns the checklist

Today the model writes `TASK.md` and must tick items with `edit_file`. In the last run it never ticked one, so a finished task shows as incomplete.

**Files:** `agent/src/thea_agent/checklist.py` (new), `capabilities.py`, `turn.py`, `toolsets.py`, `how-you-work.md`, `src-tauri/src/db.rs` (persona Method line), tests, docs.

- [ ] **Plan:** at the start of a project turn with no open checklist, one model request with `output_type=Checklist` (pydantic-ai structured output). `Checklist.items: list[Item]`, `Item(text: str, check: Literal["draft", "sources", "citations", "style", "ask", "manual"])`. Code writes `TASK.md` from it. The model does not write `TASK.md`.
- [ ] **Ticks from tool results** (a capability that watches tool returns):
  - `draft`: a file in `research/drafts/` or `docket/drafts/` with no `TODO` line.
  - `sources`: `list_sources` count is at least the budget's `min_sources`.
  - `citations`: `check_citations` returned `PASS`.
  - `style`: `check_style` returned `PASS`.
  - `ask`: the next user message arrives.
  - `manual`: the model calls a new tool `tick_item(n, evidence)`. `evidence` is one line.
- [ ] **Nudges:** the end-of-turn states stay (not started, in progress, waiting on the user, complete). They read the code's state. Our nudge count is its own counter in `TurnDeps`, not pydantic-ai's output retries, so "Please return text or call a tool." does not use it up.
- [ ] **Prompt:** "Start with TASK.md" in `how-you-work.md` and step 1 of both personas change to: "Thea writes TASK.md from your plan and ticks items when their check passes."
- [ ] Tests: the plan request, each tick rule, `tick_item`, the separate nudge count, the reset of a finished checklist.

## Part C: Edits that do not need exact text

Today the model must retype text for `old_text`. It rewrites from meaning ("What it covers" for "What the report covers"), and 2 misses end the turn.

**Files:** `agent/src/thea_agent/tools/drafts.py` (new), `tools/ste.py`, `toolsets.py`, the 7 writing skills, `write-ste.md`, tests, `docs/reference/tools-and-approvals.md`.

- [ ] `fill_section(path, heading, text)`: replaces the `TODO` line or lines under the heading. It fails when the heading is not in the file or has no `TODO` line, and the error lists the headings that still have one.
- [ ] `check_style` gives each sentence it quotes an id, like `9.1` (line 9, sentence 1), and keeps the file hash.
- [ ] `fix_sentence(path, id, text)`: replaces that sentence by position. It fails when the file changed since the last `check_style`, and the error says to run `check_style` again.
- [ ] Both are `write` tools behind the same approval as `edit_file`. `edit_file` stays for other edits.
- [ ] Skills: step 3 of each writing skill uses `fill_section`. The style step uses `fix_sentence`.
- [ ] Tests: fill one section, unknown heading, a heading with no `TODO` line, a fix by id, a stale id after an edit.

---

## Check after each part

- `just check`.
- Both suites once. Report each check for each case in a table, and explain each failure from the trace before changing anything.
