# Model Tiers and Prompt Budgets

It assigns each model to a tier based on its parameter count and context length. A model with a context window under `16384` tokens uses `Small`. A model with a context window under `32768` tokens cannot be more than `Medium`.

| Tier | Parameter Size | Workspace Tree Entries | Knowledge File Snippet | Tool Output Cap | Max Steps per Round | Search Results (`web_search`) | Sources per Round |
|---|---|---|---|---|---|---|---|
| `Small` | Under 8B | 30 | 2000 chars | 6000 chars | 30 | 5 | 3 to 5 |
| `Medium` | 8B to under 20B (or unknown) | 45 | 4000 chars | 12000 chars | 45 | 8 | 5 to 8 |
| `Large` | 20B and above | 60 | 6000 chars | 20000 chars | 60 | 10 | 8 to 12 |

Each chat turn can run up to `6` rounds. Within each round, if the model stops with no tool calls while `TASK.md` has `- [ ]` lines, Thea sends up to `4` nudges. If a tool call fails on `3` tries with the same name and arguments, Thea refuses that call in that round.
