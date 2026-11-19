# Core Plan and Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Planning and `TASK.md` rules live in the core system prompt for every persona; the `task-checklist` and `think-in-steps` skills are deleted; the eval writes per-suite results and per-case transcripts.

**Architecture:** A new `plan_section(tools: &[ToolDefinition]) -> Option<String>` in `src-tauri/src/agent/mod.rs` builds the section from the tools the turn actually offers, and `build_system_prompt` appends it. The eval binary names its results by suite and dumps each case's stored messages.

**Tech Stack:** Rust (Tauri 2), Markdown skills compiled with `include_dir!`.

**Spec:** `docs/dev/superpowers/specs/2026-11-15-core-plan-and-checklist-design.md`

## Global Constraints

- Planning: at most 5 thoughts, each under 60 words.
- Section present only when `write_file` is offered; `sequentialthinking` wording only when a tool whose name ends in `__sequentialthinking` is offered.
- Bundled skills stay under 400 words with `Use when` in the description.
- Docs under `docs/` (outside `docs/dev/superpowers/`) pass `repo_docs_pass_ste_style`.
- `just check` passes after every task.

## Review Focus

1. A request that needs answers from the user first (book-research intake) must ask and stop, not plan or write `TASK.md`. The core section says so; test in Task 1 asserts the sentence is present.
2. A custom persona without the sequential-thinking server must not be told to call a tool it lacks. Test in Task 1.
3. A persona without `write_file` gets no `TASK.md` instructions. Test in Task 1.
4. Two suites run on the same model and day must not overwrite each other's results. Test in Task 2.
5. A case id with path characters must not write a transcript outside the results folder: case ids come from repo JSON files only; the transcript name uses the same sanitizer as the model. Test in Task 2.

---

### Task 1: Core plan-and-checklist section, skills removed

**Files:**
- Modify: `src-tauri/src/agent/mod.rs` (`build_system_prompt` ~200; tests module)
- Modify: `src-tauri/src/db.rs` (both persona prompts ~557 and ~601, `personal-assistant.skill_ids`, test `personal_assistant_loads_only_its_skills`)
- Modify: `src-tauri/src/skills.rs` (tests ~230-290), `src-tauri/src/agent/task.rs` (module comment line 2)
- Delete: `skills/task-checklist.md`, `skills/think-in-steps.md`
- Modify: `skills/research-method.md` (step 2)
- Modify: `docs/explanation/agent-loop-and-rounds.md`, `docs/explanation/thinking-and-context.md`, `docs/reference/skills-and-templates.md`, `docs/reference/providers-and-personas.md`, `docs/tutorials/research-brief.md`, `CHANGELOG.md`

**Interfaces:**
- Produces: `pub fn plan_section(tools: &[ToolDefinition]) -> Option<String>`; `None` when no tool is named `write_file`.

- [ ] **Step 1: Write the failing tests in `agent/mod.rs` tests**

```rust
fn tool(name: &str) -> ToolDefinition { /* build with name, empty description and schema */ }

#[test]
fn plan_section_uses_sequential_thinking_when_offered() {
    let s = plan_section(&[tool("write_file"), tool("mcp__sequential_thinking__sequentialthinking")]).unwrap();
    assert!(s.contains("sequentialthinking"));
    assert!(s.contains("at most 5 thoughts"));
    assert!(s.contains("If the request needs no tools, answer directly"));
    assert!(s.contains("ask them and stop"));
    assert!(s.contains("## Done when"));
}

#[test]
fn plan_section_falls_back_without_sequential_thinking() {
    let s = plan_section(&[tool("write_file")]).unwrap();
    assert!(!s.contains("sequentialthinking"));
    assert!(s.contains("Plan in a few short lines"));
}

#[test]
fn plan_section_needs_write_file() {
    assert!(plan_section(&[tool("web_search")]).is_none());
}
```

In `db.rs` tests, replace the skill assertions in `personal_assistant_loads_only_its_skills` and add:

```rust
#[test]
fn no_persona_names_the_removed_skills() {
    for p in default_personas() {
        for gone in ["task-checklist", "think-in-steps"] {
            assert!(!p.system_prompt.contains(gone), "{} prompt names {gone}", p.id);
            assert!(!p.skill_ids.iter().any(|s| s == gone), "{} lists {gone}", p.id);
        }
    }
}
```

In `skills.rs` tests: drop the two names from `bundled_skills_parse_and_are_short`, add `assert!(!names.contains(&"task-checklist") && !names.contains(&"think-in-steps"));`, and use `write-ste` instead of `think-in-steps` in the two enable/disable tests.

- [ ] **Step 2: Run them to verify they fail**

Run: `cargo test --manifest-path src-tauri/Cargo.toml -- plan_section no_persona_names bundled_skills`
Expected: FAIL (`plan_section` not defined).

- [ ] **Step 3: Implement `plan_section` and append it in `build_system_prompt` right after the persona block**

Exact text (`{plan}` is the sequential-thinking or fallback line):

```text
## Plan, then checklist
Assess the request first. If the request needs no tools, answer directly. Do not plan and do not write TASK.md. If you need answers from the user before you can start, ask them and stop.
Otherwise:
1. {plan}
2. Write TASK.md in the workspace root with write_file, from your plan:
       # Task
       One sentence: what the user asked for.
       ## Done when
       - [ ] One item per line. Copy numbers, names and paths from the request.
3. Tick an item with edit_file (`- [ ]` to `- [x]`) only after the tool that proves it ran in this turn. Add only items that a tool you have can prove.
4. Never say a file is written unless write_file or edit_file returned "Wrote". Write a long draft in parts: write_file for the first part, edit_file to append each next part.
5. If the request changes, rewrite TASK.md. Never ask whether to continue. Do the next open item.
6. A task can take several rounds. Each round starts with a fresh context. TASK.md and your notes carry over, so keep them current.
7. When every item is ticked, reply with the deliverable path and three lines on what it contains.
```

`{plan}` with sequential thinking: `Plan with the sequentialthinking tool in at most 5 thoughts, each under 60 words. Thought 1 states what was asked. The middle thoughts list the steps and the tool for each. The last thought lists what "done" means, using only tools you have, and sets nextThoughtNeeded to false. thoughtNumber and totalThoughts are integers: {"thought": "List the steps.", "thoughtNumber": 1, "totalThoughts": 3, "nextThoughtNeeded": true}. After each batch of results, add one thought: what you learned and what is still missing.`

`{plan}` fallback: `Plan in a few short lines: what was asked, the steps and the tool for each, and what "done" means, using only tools you have.`

- [ ] **Step 4: Remove the skills and their references**

- Delete `skills/task-checklist.md` and `skills/think-in-steps.md`.
- `db.rs` Personal Assistant step 1: `1. Plan, then write TASK.md (see Plan, then checklist).` Research Assistant step 1: `1. Plan, then write TASK.md. For a paper, proposal, essay or review, follow the deep-research skill; for a book, book-research. Otherwise load research-method.`
- `personal-assistant.skill_ids`: `manage-docket`, `draft-communication`, `weekly-review`, `write-ste`.
- `skills/research-method.md` step 2: `2. Plan as the system prompt says, in at most 5 thoughts.`
- `agent/task.rs` line 2: `//! checklist (core prompt, "Plan, then checklist"); the loop keeps a turn alive while items are open.`
- Leave `skills/book-research.md` unchanged: its intake already asks and waits, which the core section now allows ("ask them and stop").

- [ ] **Step 5: Run the tests**

Run: `just check`
Expected: exit 0.

- [ ] **Step 6: Docs**

- `agent-loop-and-rounds.md` line 9: the core system prompt, not the `task-checklist` skill, tells the model to plan and write `TASK.md`, and to answer directly when the request needs no tools.
- `thinking-and-context.md` line 15: the core system prompt, not the `think-in-steps` skill, sets the 5-thought plan.
- `skills-and-templates.md`: remove the two rows.
- `providers-and-personas.md`: Personal Assistant skill list without the two skills.
- `research-brief.md` line 45: "It plans with `sequentialthinking` and writes `TASK.md` in the project root."
- `CHANGELOG.md` Changed: "- Planning and the `TASK.md` checklist are part of the core prompt for every persona. The model plans only when the request needs tools. The `task-checklist` and `think-in-steps` skills are gone." Update the "Ten bundled skills" Added line to drop "task checklist" and "step-by-step thinking".
- Run `just check` again. Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add -A skills src-tauri/src docs CHANGELOG.md
git commit -m "feat: plan and TASK.md checklist in the core prompt; remove task-checklist and think-in-steps skills"
```

### Task 2: Eval results per suite, transcripts per case

**Files:**
- Modify: `src-tauri/src/bin/eval.rs` (`main` ~240-324, `run_case` ~200)
- Modify: `justfile` (`eval` recipe), `docs/dev/how-to/run-eval.md`

**Interfaces:**
- Produces: `fn sanitize(s: &str) -> String` (the existing model sanitizer, extracted) and `fn results_stem(cases_dir: &str, model: &str, date: &str) -> String` = `"<sanitize(last path component of cases_dir)>-<sanitize(model)>-<date>"`.
- Produces: results at `evals/results/<stem>.json`; transcripts at `evals/results/<stem>/<sanitize(case id)>.json`, each the case's `Vec<StoredMessage>` as pretty JSON.

- [ ] **Step 1: Write the failing tests in `eval.rs`**

```rust
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn results_stem_includes_the_suite() {
        assert_eq!(results_stem("evals/assistant", "gemma4:e4b-mlx", "2026-11-15"), "assistant-gemma4-e4b-mlx-2026-11-15");
        assert_eq!(results_stem("evals/research/", "m", "d"), "research-m-d");
    }
    #[test]
    fn sanitize_keeps_names_inside_one_folder() {
        assert_eq!(sanitize("../x/y"), "..-x-y");
        assert!(!sanitize("../x/y").contains('/'));
    }
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cargo test --manifest-path src-tauri/Cargo.toml --bin eval`
Expected: FAIL (`results_stem` not defined).

- [ ] **Step 3: Implement**

`results_stem` uses `Path::new(cases_dir).file_name()` (handles the trailing slash). In `run_case`, after `list_messages`, keep the messages on the result (`#[serde(skip)] messages: Vec<StoredMessage>` on `CaseResult`); in `main`, write each case's transcript under `evals/results/<stem>/`. `justfile`: `eval model="gemma4:e4b" cases="evals/research":` passing `--cases {{cases}}`.

- [ ] **Step 4: Run the tests**

Run: `just check`
Expected: exit 0.

- [ ] **Step 5: Docs**

`run-eval.md`: add a step for `just eval gemma4:e4b evals/assistant`, and state that results go to `evals/results/<suite>-<model>-<date>.json` with one transcript per case in the folder of the same name. Run `just check`. Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add src-tauri/src/bin/eval.rs justfile docs/dev/how-to/run-eval.md
git commit -m "fix(eval): name results by suite and save a transcript for each case"
```

### Task 3: Re-run the evals

- [ ] **Step 1:** `just eval gemma4:e4b-mlx evals/assistant` then `just eval gemma4:e4b-mlx evals/research`.
- [ ] **Step 2:** Compare with the baseline (assistant: schedule-kickoff FAIL at 2 steps, 0 planning thoughts in all 3; research: reflexion FAIL, planning thoughts in 2 of 5). Read the schedule-kickoff transcript if it still fails.
