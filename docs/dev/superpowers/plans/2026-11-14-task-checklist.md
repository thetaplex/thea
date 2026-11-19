# Task Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The agent loop keeps working while `TASK.md` has open checklist items; the checklist procedure is a skill loaded on demand; the persona prompt carries one rule.

**Architecture:** Standard split. Persona prompt: identity and invariants. Skills: progressive disclosure, listed by description, loaded with `load_skill`, any number per turn. Loop: one generic signal, open `- [ ]` items in `<project>/TASK.md`, nudged back up to 4 times per turn. The two text heuristics from 2026-11-14 are deleted.

**Tech Stack:** Rust (Tauri 2 backend), bundled skills via `include_dir!`.

**Spec:** `docs/superpowers/specs/2026-11-14-task-checklist-design.md` (the "Skill inlined in the prompt" section is superseded by this plan: no inline flag).

## Global Constraints

- Task file: `TASK.md` in the project root, exact name.
- Open item: a line that, trimmed, starts with `- [ ]`. Done: `- [x]` or `- [X]`.
- Nudge cap: 4 per turn, inside the step cap.
- Nudge text: `TASK.md still has open items:\n<open lines>\nDo the next one now. Tick it with edit_file when its proof has run.` Ephemeral `user` message in `chat_messages` only, never stored.
- Skill descriptions say when to use the skill, so the model can pick several per turn.
- Bundled skill bodies under 400 words; Research Assistant prompt under 200 words (existing tests).
- No new crates.

## Review Focus

- `TASK.md` fully ticked or without a checklist: turn ends as today. Task 1.
- `TASK.md` missing or no project: no nudge, no error. Task 1.
- A model that never ticks: 4 nudges then stop. Task 1 (cap arithmetic in the loop, helper tested).
- Skill descriptions each contain a "Use when" cue. Task 2.

---

### Task 1: `TASK.md` keeps the turn alive

**Files:**
- Create: `src-tauri/src/agent/task.rs`
- Modify: `src-tauri/src/agent/mod.rs` (`pub mod task;`, nudge block in the loop, delete `MAX_CONTINUE_NUDGES`, `CONTINUE_NUDGE`, `announces_next_step`, `claimed_missing_file` and their two tests)

**Interfaces:**
- Produces: `task::TASK_FILE: &str = "TASK.md"`, `task::MAX_NUDGES: usize = 4`, `task::open_items(markdown: &str) -> Vec<String>`, `task::nudge_for(root: &Path) -> Option<String>`.

- [ ] **Step 1: Failing tests** (in `task.rs`)

```rust
#[test]
fn open_items_finds_unchecked_lines_only() {
    let md = "# Task\nGoal\n\n## Done when\n- [ ] Draft at research/drafts/a.md\n- [x] Sources registered\n  - [ ] indented counts\n- [X] upper done\n- not a box\n";
    assert_eq!(open_items(md), vec!["- [ ] Draft at research/drafts/a.md", "- [ ] indented counts"]);
}
#[test]
fn nudge_only_when_file_has_open_items() {
    let dir = tempfile::tempdir().unwrap();
    assert_eq!(nudge_for(dir.path()), None);
    std::fs::write(dir.path().join("TASK.md"), "- [x] done\n").unwrap();
    assert_eq!(nudge_for(dir.path()), None);
    std::fs::write(dir.path().join("TASK.md"), "- [ ] one\n- [ ] two\n").unwrap();
    assert_eq!(nudge_for(dir.path()).unwrap(), "TASK.md still has open items:\n- [ ] one\n- [ ] two\nDo the next one now. Tick it with edit_file when its proof has run.");
}
```

- [ ] **Step 2: Run** `cargo test --manifest-path src-tauri/Cargo.toml --lib agent::task::` → FAIL, module missing.
- [ ] **Step 3: Implement `task.rs`; in the loop replace the text-only branch:**

```rust
if turn.tool_calls.is_empty() {
    let next = (nudges_left > 0)
        .then(|| project_root_buf.as_deref().and_then(task::nudge_for))
        .flatten();
    match next {
        Some(text) => { nudges_left -= 1; nudge = Some(text); continue; }
        None => break,
    }
}
```

`nudges_left` starts at `task::MAX_NUDGES`. Delete the heuristics and their tests.

- [ ] **Step 4: Run** `cargo test --manifest-path src-tauri/Cargo.toml --lib && cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings` → PASS, clean.
- [ ] **Step 5: Commit** `feat(agent): TASK.md open items keep the turn alive; drop text heuristics`

### Task 2: `task-checklist` skill, persona rule, "Use when" descriptions, docs

**Files:**
- Create: `skills/task-checklist.md`
- Modify: `skills/*.md` descriptions, `src-tauri/src/db.rs` Research Assistant prompt, `src-tauri/src/skills.rs` test name list, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: Extend `bundled_skills_parse_and_are_short`:** add `"task-checklist"` to the name list and `assert!(x.description.contains("Use when"), "{}", x.name)` in the per-skill loop.
- [ ] **Step 2: Run** it → FAIL.
- [ ] **Step 3: Write `skills/task-checklist.md`:**

```markdown
---
description: Use when a request has a deliverable with criteria (a draft, a report, a length, checks). How to write and maintain TASK.md so the work runs to completion.
---
# Task checklist

Write TASK.md in the project root with write_file before any other step:

    # Task
    One sentence: what the user asked for.

    ## Done when
    - [ ] Draft at research/drafts/<name>.md, <length or sections from the request>
    - [ ] Every claim cites a ledger key
    - [ ] check_style run on the final draft, violations fixed
    - [ ] check_citations PASS on the final draft

Rules:
- One criterion per line. Copy numbers, names and paths from the request.
- Tick an item with edit_file (`- [ ]` to `- [x]`) only after the tool that proves it ran in this turn.
- Never say a file is written unless write_file or edit_file returned "Wrote".
- Long drafts: write_file for the first part, edit_file to append each next part.
- If the request changes, rewrite TASK.md.
- Never ask whether to continue. Do the next open item.
- When every item is ticked, reply with the deliverable path and three lines on what it contains.
```

- [ ] **Step 4: Descriptions.** Rewrite each existing bundled skill's `description:` to start with "Use when ...": research-method (framing a question or starting a search), source-triage (judging a search result before reading it), write-research-paper (drafting a paper), write-research-proposal (drafting a proposal), write-ste (writing or revising any draft), think-in-steps (planning before a multi-step task).
- [ ] **Step 5: Persona prompt.** Method line 1 becomes `1. Load the task-checklist skill and write TASK.md. Load the research-method skill. Plan with the sequentialthinking tool.` Remove the two rules added 2026-11-14 (`Long documents go in files...`, `Never ask whether to continue...`); the skill carries them. Stay under 200 words.
- [ ] **Step 6: Docs.** README skills line: add "Skills are loaded on demand, several per turn when relevant." CHANGELOG: "Seven bundled skills: task checklist, research method, ..." and "- `TASK.md` checklist: the agent keeps working while it has open items, up to four nudges per turn."
- [ ] **Step 7: Run** `just check` → exit 0.
- [ ] **Step 8: Commit** `feat(skills): task-checklist skill; skill descriptions say when to use them`
