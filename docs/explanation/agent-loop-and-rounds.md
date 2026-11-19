# The Agent Loop, `TASK.md`, and Rounds

This guide explains how the loop for the agent keeps a small model on track during a long task.

A small model on your machine can stop early. A model may reply with its plan for the next step instead of calling a tool. Or it may fill its context window with web pages before it writes a draft. The loop of the agent solves these two problems.

## Checklist-Driven Completion (`TASK.md`)

`TASK.md` is for projects only. A chat without a project does not use it. In a project, the first tool call of the model writes `TASK.md` in the project root. Each deliverable criterion is an unchecked box (`- [ ]`).

At the start of a turn, Thea empties a `TASK.md` that has no open items, so a new request starts with a new checklist. A `TASK.md` with open items stays, so the turn continues the task.

When the model replies with text and no tool calls, the agent loop reads `TASK.md` and does one of these:

| State of `TASK.md` | Meaning | Result |
|---|---|---|
| No items | The task did not start | 1 nudge: write `TASK.md`, then do the first item. After this nudge, the reply is the answer. |
| The next open item starts with `Ask the user` | The model waits for the user | The turn ends. The next turn continues the task. |
| Open items | The task is in progress | A nudge lists the open items, up to `4` in each round. |
| All items are `[x]` or `[!]` | The task is complete | The turn ends. |

A nudge is an ephemeral user message. It tells the model to do the next item and tick it with `edit_file`.

## Multi-Round Context Reset

Each model tier has a limit on model requests in a round (`30` for `Small`, `45` for `Medium`, and `60` for `Large`). When a round reaches that limit and `TASK.md` still has open `- [ ]` items, Thea does not abort the task. On the last request of a round, it removes all tools and asks the model for a status summary. Then it does this:

1. It keeps the 8-line status summary of the model.
2. It starts a new round (up to `6` rounds) with a fresh message history.
3. It drops the old tool outputs from earlier rounds. It sends a short brief with the request, the last status, and the current `TASK.md`.
4. The model continues from the notes in `research/notes.md` and the sources in `research/sources.json`.

This design keeps the size of the prompt within a context window of `32768` tokens during a long research run.

## Detection of Repeated Tool Calls

Small models can get stuck calling the same failing URL in a loop. The `DetectLoops` capability of `pydantic-ai-harness` watches the recent tool calls and results. When it sees the same call, the same result, or an alternating pattern repeat, it adds a nudge to the chat. The nudge tells the model to change its approach or to explain what blocks it. A nudge does not stop the turn.
