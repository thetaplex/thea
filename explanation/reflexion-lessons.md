# Self-Improvement with `Reflexion` Lessons

This guide explains how the app records and reuses lessons for each persona.

Thea learns from signals without a change to the weights of the model.

A reflection call runs in the background after a turn only when 1 of 3 signals happens:

1. `check_citations`: the last citation check in the turn passed or failed.
2. `rating_up` or `rating_down`: the user clicked thumbs-up or thumbs-down on the final reply.
3. `repeated_errors`: the same tool failed `3` or more times with the same error prefix during the turn.

It summarizes the task, the final answer, and the recent tool calls (up to `4000` characters). Then it asks the model for 1 rule of at most `2` sentences that starts with `When`. Valid lessons go into `~/.thea/lessons/<persona-id>.md` (up to `20` lessons per persona, oldest dropped first). It adds those lessons to future system prompts for that persona.
