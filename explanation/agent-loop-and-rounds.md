# The Agent Loop, `TASK.md`, and Rounds

This guide explains how the loop for the agent keeps a small model on track during a long task.

A small model on your machine can stop early. A model may reply with its plan for the next step instead of calling a tool. Or it may fill its context window with web pages before it writes a draft. The loop of the agent solves these two problems.

## Checklist-Driven Completion (`TASK.md`)

The `task-checklist` skill tells the model to write `TASK.md` in the project root before any other step. Each deliverable criterion is an unchecked box (`- [ ]`).

When the model replies with text and no tool calls, the agent loop reads `<project>/TASK.md`. If a `- [ ]` line is still open, the turn does not end. The loop adds an ephemeral user message (a nudge) that lists the open items. The nudge tells the model to do the next item and tick it with `edit_file`. The loop sends up to `4` nudges in each round.

## Multi-Round Context Reset

Each model tier has a limit on steps in a round (`30` for `Small`, `45` for `Medium`, and `60` for `Large`). When a round reaches its step limit on a tool call and `TASK.md` still has open `- [ ]` items, Thea does not abort the task:

1. It makes a call with no tools and asks the model for an 8-line status summary.
2. It starts a new round (up to `6` rounds) with a fresh message history.
3. It drops the old tool outputs from earlier rounds. It sends a short brief with the request, the last status, and the current `TASK.md`.
4. The model continues from the notes in `research/notes.md` and the sources in `research/sources.json`.

This design keeps the size of the prompt within a context window of `32768` tokens during a long research run.

## Refusal of Repeated Failing Tool Calls

Small models can get stuck calling the same failing URL in a loop. The loop for the agent tracks the `(tool_name, arguments)` pair of each call in the round. After `3` failures, it refuses to run that call again. It tells the model to pick another source or go to the next item in `TASK.md`.
