# Close Source and Docs Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the open-source license and scaffolding, hide built-in skills from the Skills pane, and split `docs/` into a user tree and a `docs/dev/` developer tree.

**Architecture:** Text and file moves, plus one filter in the Rust `list_skills` IPC path. The STE style test in `src-tauri/src/tools/ste.rs` is the gate for every Markdown change.

**Tech Stack:** Rust (Tauri 2), Markdown, `just`, `cargo test`.

**Spec:** `docs/dev/superpowers/specs/2026-11-15-close-source-and-docs-split-design.md`

## Global Constraints

- Every Markdown page under `README.md`, `docs/`, and `docs/dev/` passes `check_style` (test `repo_docs_pass_ste_style`).
- No page under `docs/` (outside `docs/dev/`) names a Rust source path, a Rust constant, or a `just` recipe.
- No content is deleted; it moves or is trimmed into the architecture page.
- Branch from `docs/diataxis-and-readme` (PR 17), not `main`.
- Copyright holder is `ThetaPlex`, year `2026`.

## Review Focus

- A `load_skill` call for a built-in skill from the agent must still work after the pane filter (Task 2 test).
- A custom skill with the same name as a hidden built-in must still appear in the pane (Task 2 test).
- Every relative link in `docs/README.md` and `docs/dev/README.md` must resolve (Task 3 link check).
- `docs/dev/` must contain at least one `.md` per walked folder or the style test's `count > 0` assertion fails (Task 3).
- User tutorials still say `just run` because no installer exists yet; the plan leaves that and records it in `docs/dev/README.md` as a known gap (Task 5).

---

### Task 1: License and scaffolding

**Files:**
- Modify: `LICENSE`, `package.json:41`, `src-tauri/Cargo.toml:6`, `README.md:97-104`
- Delete: `NOTICE`, `CONTRIBUTING.md`

- [ ] **Step 1: Replace `LICENSE`** with exactly:

```
Copyright 2026 ThetaPlex. All rights reserved.

This software and its source code are proprietary. No license, express or
implied, is granted to any person to use, copy, modify, or distribute this
software or any part of it without written permission from ThetaPlex.
```

- [ ] **Step 2: Delete `NOTICE` and `CONTRIBUTING.md`** with `git rm`.
- [ ] **Step 3: Set license fields.** `package.json`: `"license": "UNLICENSED"`. `Cargo.toml`: `license = "LicenseRef-Proprietary"`.
- [ ] **Step 4: README.** Remove the `## Links` and `## License` sections. Keep `CHANGELOG.md` reachable: add `- [Changelog](CHANGELOG.md)` under `## Documentation`.
- [ ] **Step 5: Verify.** Run `grep -rn -e Apache -e NOTICE -e CONTRIBUTING -e CODE_OF_CONDUCT -e SECURITY.md README.md CHANGELOG.md docs package.json src-tauri/Cargo.toml`. Expected: no output.
- [ ] **Step 6: Commit.** `chore: close the source; proprietary license, drop open-source scaffolding`

### Task 2: Hide built-in skills from the pane

**Files:**
- Modify: `src-tauri/src/skills.rs` (add function + tests), `src-tauri/src/lib.rs:485-492`
- Modify: `src/components/SkillsPane.tsx:78` (header label)

**Interfaces:**
- Produces: `pub fn visible_skills(db: &Database, project_root: Option<&Path>) -> Vec<SkillInfo>` in `skills.rs`. Same as `discover_skills` minus entries with `source == "builtin"`.

- [ ] **Step 1: Write the failing tests** in the `tests` module of `skills.rs`, following the pattern of `global_skill_overrides_builtin_and_disabled_list_applies` for the temp `THEA_HOME` and `Database` setup:

```rust
#[test]
fn visible_skills_hides_builtins() {
    // setup as in the existing test
    let v = visible_skills(&db, None);
    assert!(v.iter().all(|s| s.source != "builtin"));
    assert!(discover_skills(&db, None).iter().any(|s| s.source == "builtin"));
}

#[test]
fn visible_skills_keeps_custom_skill_that_shadows_a_builtin() {
    // create a global custom skill named "write-ste" via create_custom_skill
    let v = visible_skills(&db, None);
    assert!(v.iter().any(|s| s.name == "write-ste" && s.source == "global"));
}
```

- [ ] **Step 2: Run** `cargo test --manifest-path src-tauri/Cargo.toml visible_skills`. Expected: compile error, `visible_skills` not found.
- [ ] **Step 3: Implement `visible_skills`** in `skills.rs` as a filter over `discover_skills`.
- [ ] **Step 4: Switch `list_skills` in `lib.rs`** to call `skills::visible_skills`. Leave `agent/mod.rs:455` on `discover_skills` so `load_skill` still sees built-ins.
- [ ] **Step 5: Pane label.** In `SkillsPane.tsx:78` change `Skills Library` to `Custom Skills`.
- [ ] **Step 6: Run** `cargo test --manifest-path src-tauri/Cargo.toml skills`. Expected: all pass.
- [ ] **Step 7: Commit.** `feat(skills): hide built-in skills from the Skills pane`

### Task 3: Move developer pages to `docs/dev/`

**Files:**
- Move with `git mv`: `docs/how-to/run-eval.md` → `docs/dev/how-to/run-eval.md`; `docs/how-to/build-installers.md` → `docs/dev/how-to/build-installers.md`; `docs/explanation/architecture.md` → `docs/dev/explanation/architecture.md`; `docs/reference/cli-and-ste-rules.md` → `docs/dev/reference/cli-and-ste-rules.md`; `docs/superpowers/` → `docs/dev/superpowers/` (the two specs and two plans already there).
- Create: `docs/dev/README.md`
- Modify: `docs/README.md` (drop the four moved links), `src-tauri/src/tools/ste.rs:646-660`

- [ ] **Step 1: Extend the style test.** Add `"docs/dev/how-to"`, `"docs/dev/explanation"`, `"docs/dev/reference"` to the `dir` array and `"docs/dev/README.md"` to the `rel` array in `repo_docs_pass_ste_style`. Run it. Expected: FAIL, `docs/dev/how-to` does not exist.
- [ ] **Step 2: Move the files** with `git mv` as listed.
- [ ] **Step 3: Write `docs/dev/README.md`.** Title `Thea Developer Documentation`. One sentence: these pages are for people who build Thea from source; user pages are in `docs/`. Then Diátaxis sections How-To (2 links), Reference (1 link), Explanation (1 link), and a `## Design Documents` section linking `superpowers/specs/` and `superpowers/plans/` as folders. End with `## Known Gaps` holding one bullet: user tutorials start from `just run` until a first installer release exists.
- [ ] **Step 4: Update `docs/README.md`.** Remove lines 25, 26, 37, 43 (the four moved pages). Add one line at the end: `Developer documentation is in [docs/dev/](dev/README.md).`
- [ ] **Step 5: Fix inbound links.** `grep -rn "architecture.md\|run-eval.md\|build-installers.md\|cli-and-ste-rules.md" README.md docs` and repoint each hit to the `dev/` path or remove it from a user page.
- [ ] **Step 6: Link check.** Run from repo root:

```bash
grep -rhoE '\]\(([^)#]+\.md)' docs/README.md docs/dev/README.md | sed 's/](//' | while read l; do d=$(grep -l "$l" docs/README.md docs/dev/README.md | head -1 | xargs dirname); test -f "$d/$l" || echo "BROKEN $l"; done
```
Expected: no `BROKEN` lines.
- [ ] **Step 7: Run** `cargo test --manifest-path src-tauri/Cargo.toml repo_docs_pass_ste_style`. Expected: PASS.
- [ ] **Step 8: Commit.** `docs: move developer pages to docs/dev`

### Task 4: Trim source references from user pages

**Files:**
- Modify: `docs/explanation/reflexion-lessons.md:5`, `docs/explanation/agent-loop-and-rounds.md:5,11,18`, `docs/explanation/security-model.md:5,7`, `docs/reference/tiers-and-budgets.md:11`, `docs/how-to/local-search-searxng.md:8`, `docs/tutorials/research-brief.md:19`
- Modify: `docs/dev/explanation/architecture.md` (receives moved paragraphs)

- [ ] **Step 1: Define the test.** Run from repo root:

```bash
grep -rnE 'src-tauri/|src/[a-z]|MAX_[A-Z]|\.rs\b|just [a-z]' docs --exclude-dir=dev
```
Expected now: 9 hits. Target: 0 hits. (`skills-and-templates.md` lists `src/main.py` inside a template table; that is a template file, keep it, and tighten the pattern to `src/[a-z]+\.rs` if it trips.)
- [ ] **Step 2: Trim each hit.** Rules: a file path becomes a plain-language subject ("the agent loop", "the path sandbox", "the lessons module"); a constant becomes its number ("up to 6 rounds"); `just searxng` becomes the `docker run` command copied verbatim from the `justfile` `searxng` recipe, as a fenced block. Where a sentence only explains where code lives, cut it and append it under a `## Code Map` heading in `docs/dev/explanation/architecture.md`.
- [ ] **Step 3: Re-run the grep from Step 1.** Expected: no output.
- [ ] **Step 4: Run** `cargo test --manifest-path src-tauri/Cargo.toml repo_docs_pass_ste_style`. Expected: PASS. Fix any new STE violations it reports.
- [ ] **Step 5: Commit.** `docs: remove source paths and constants from user pages`

### Task 5: Two READMEs

**Files:**
- Rewrite: `README.md`
- Modify: `docs/README.md` (first section)

- [ ] **Step 1: Developer `README.md`.** Sections in order: `# Thea`; one paragraph copied from the first paragraph of `docs/README.md`; `## Prerequisites` (Rust, pnpm, just, Ollama, Docker optional, Node 24 optional, with links); `## Commands` as the existing table of `just` recipes; `## Documentation` with two bullets, user docs at `docs/README.md` and developer docs at `docs/dev/README.md`, plus the Changelog link; `## Known Limitations` unchanged. Drop Personas, Main Features, Install, Quickstart; they live in `docs/README.md` now.
- [ ] **Step 2: Public `docs/README.md`.** Move the `## Personas` table and `## Main Features` list from the old README into it, after the intro paragraph and before `## Tutorials`. Add a `## Download` section with one sentence: installers for macOS and Windows will be on the Releases page of the public repository; until then build from source with the developer README.
- [ ] **Step 3: Run** `cargo test --manifest-path src-tauri/Cargo.toml repo_docs_pass_ste_style`. Expected: PASS.
- [ ] **Step 4: Full check.** Run `just check`. Expected: exit 0.
- [ ] **Step 5: Commit.** `docs: developer README in the repo, product README in docs/`
- [ ] **Step 6: Changelog.** Add under `Unreleased` → `Changed`: `- Proprietary license; the repository is no longer open source.`, `- Built-in skills no longer appear in the Skills pane.`, `- Developer documentation moved to docs/dev/.` Commit `docs: changelog for close-source and docs split`.
