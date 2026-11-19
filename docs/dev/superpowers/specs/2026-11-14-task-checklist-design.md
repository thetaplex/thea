# Task checklist as the done signal

Date: 2026-11-14. Supplements the 2026-11-13 Research Assistant design.

## Intent

The agent loop ends a turn when the model replies without a tool call. Small models
end turns by announcing the next step, or by claiming a file was written when it was
not, so work stops early and the user has to type "continue". The loop should instead
know what the task is and keep working until it is done.

## Goals

- The pipeline lives in a skill, not in Rust. Editing it needs no rebuild.
- "Done" is an explicit, visible checklist on disk, not an inference from text.
- The mechanism is persona-independent. Nothing in Rust knows what research is.

## Non-goals

- Verifying each criterion mechanically. The skill tells the model to tick an item
  only after the tool that proves it has run; the loop trusts the checklist.
- A second model call to judge completion.

## Approaches considered

1. Skill only, keep today's text heuristics. Cheapest; completion still inferred
   from the model's words, which is what failed.
2. Skill plus a task file with a checklist, loop keeps going while items are open.
   Chosen: observable, generic, visible in the Files pane, about 40 lines of Rust.
3. Skill plus a verifier model call. Handles fuzzy criteria; doubles model cost and
   makes a 4B judge the weak point.

## Design

### Skill inlined in the prompt

- Skill front matter gains `inline: true`. The system prompt includes the full body of
  every enabled inline skill under `## Method`, instead of listing it for `load_skill`.
- New bundled skill `research-pipeline.md` with `inline: true`. It holds the whole
  method that today sits in the Research Assistant system prompt: plan, search, read,
  register sources, write notes, draft to a file, `check_style`, `check_citations`,
  plus the task-file rules below. The persona prompt keeps only identity and rules.
- `research-method.md` stays as the search sub-procedure the pipeline refers to.

### Task file

Path `TASK.md` in the project root. The skill tells the model to write it before any
other step, from the user's request:

```markdown
# Task
One sentence: what the user asked for.

## Done when
- [ ] Draft at research/drafts/<name>.md, at least 5000 words
- [ ] Every claim cites a ledger key
- [ ] check_style run on the final draft, violations fixed
- [ ] check_citations PASS on the final draft
```

Rules in the skill: one criterion per line; copy numbers and names from the request;
tick an item with `edit_file` only after the tool that proves it ran in this turn; if
the user changes the request, rewrite the file.

### Loop rule

In `run_agent_turn_with_reflection`, when a reply has no tool calls:

- If `TASK.md` exists in the project root and contains at least one `- [ ]` line, the
  turn is not over. Append an ephemeral user message: "TASK.md still has open items:
  <the lines>. Do the next one now. Tick it with edit_file when its proof has run."
  Continue the loop. Cap: 4 such nudges per turn, inside the step cap.
- Otherwise the turn ends as today.

The two text heuristics added on 2026-11-14 (`announces_next_step`,
`claimed_missing_file`) are removed. The task file replaces both.

### Out of scope, noted

- A checklist badge in the chat header. The Files pane shows `TASK.md` already.
- Eval scoring on `TASK.md` state. Add once the file format has settled.

## Costs if wrong

- A model that ticks items without proof ends early, as today, no worse.
- A model that never ticks runs to the nudge cap, four extra steps, then stops.
