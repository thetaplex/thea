# Core prompt: plan, then checklist

Date: 2026-11-15. Status: approved, not implemented.

## Intent

`TASK.md` drives the agent loop (nudges, rounds), but its rules live in the optional `task-checklist` skill, whose template is research-only (`research/drafts/`, sources, `check_citations`). The Personal Assistant loads it and gets a checklist it cannot satisfy. Planning (`think-in-steps`) is also a skill, so a small model may skip it or loop in it (a real run made 13 `sequentialthinking` calls without a checklist).

Planning and the checklist are how every tool-using task runs, so they belong in the core prompt, and the checklist comes from the plan for that request rather than a fixed template.

## Goals

- Every persona's system prompt carries one "Plan, then checklist" section built by `build_system_prompt`.
- The model assesses the request: a request that needs no tools gets a direct answer, with no plan and no `TASK.md`.
- Otherwise it plans in at most 5 `sequentialthinking` thoughts, the last one listing the Done-when items, and then writes `TASK.md` from that list.
- `skills/task-checklist.md` and `skills/think-in-steps.md` are deleted.

## Non-goals

- A code nudge when the model plans without writing `TASK.md`. Add it only if the evals show the planning loop again.
- Changing how `agent/task.rs` parses `TASK.md` or how nudges and rounds work.

## Approaches

| Approach | Trade-off | Outcome |
|---|---|---|
| Core prompt section; checklist designed in the plan | One source of truth next to the code that reads `TASK.md`; relies on the model's plan | Chosen |
| One shared skill with per-persona example templates | Small model may copy both examples; still optional to load | Rejected |
| A separate checklist skill per persona | Two copies of the same rules drift | Rejected |

## Design

### Core section (in `build_system_prompt`, every persona)

Content, about 150 words, in `ASD-STE100` style:

1. Assess the request. If it needs no tools, answer directly. Do not plan and do not write `TASK.md`.
2. Otherwise plan first with `sequentialthinking`: at most 5 thoughts, each under 60 words. Thought 1 states what was asked. The middle thoughts list the steps and the tool for each. The last thought lists what "done" means, using only tools you have, and sets `nextThoughtNeeded` to false. `thoughtNumber` and `totalThoughts` are integers (one JSON example).
3. Write `TASK.md` with `write_file` from the last thought: `# Task`, one sentence; `## Done when`, one `- [ ]` item per line.
4. Rules: tick an item with `edit_file` only after the tool that proves it ran; add only items a tool you have can prove; never say a file is written unless the tool returned "Wrote"; write long drafts in parts; rewrite `TASK.md` if the request changes; never ask whether to continue; each round starts fresh, so `TASK.md` and your notes carry over; when every item is ticked, reply with the deliverable path and three lines on its content.
5. While working, after each batch of results, one thought: what you learned and what is still missing.

When the persona has no `sequentialthinking` tool, point 2 reads "plan in a few short lines" and the rest is unchanged. When it has no `write_file`, the section is left out.

### References to update

- Persona prompts in `src-tauri/src/db.rs`: step 1 of both personas stops naming the two skills.
- `personal-assistant.skill_ids`: drop the two skills.
- `skills/research-method.md`: drop "(think-in-steps skill)".
- `skills/book-research.md`: intake becomes "ask your questions and stop; plan on the next turn".
- `src-tauri/src/skills.rs` tests that use `think-in-steps`; comment in `src-tauri/src/agent/task.rs`.
- Docs: `explanation/agent-loop-and-rounds.md`, `explanation/thinking-and-context.md`, `reference/skills-and-templates.md`, `reference/providers-and-personas.md`, `tutorials/research-brief.md`, `CHANGELOG.md`.

### Tests

- The prompt has the section, with the `sequentialthinking` wording when that tool is present and the fallback when it is not, and leaves it out without `write_file`.
- Neither skill exists in `builtin_skills()`.
- No built-in persona prompt or `skill_ids` names either skill.

### Verification

Re-run `evals/assistant` and `evals/research` with `gemma4:e4b-mlx` and compare with the baseline run made before this change.
