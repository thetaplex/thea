# Thinking Modes and Context Window Sizing

This guide explains why the `Research Assistant` uses `sequential-thinking` and how Thea sizes the context window.

## Why the `Research Assistant` Uses `sequential-thinking`

For the `Research Assistant` persona, Thea sets `native_thinking: false` (which sends `think: false` to `Ollama`) and links the `sequential-thinking` `MCP` server instead.

Hidden native thinking tokens have 3 drawbacks on small local models:

- They can run for thousands of tokens without a cap and consume the step budget.
- They are invisible when collapsed or stripped by the provider.
- They leave no messages from tools in SQLite for post-turn reflection.

With the `sequentialthinking` tool and the `think-in-steps` skill, the model plans in at most `5` short thoughts under `60` words each. It stores every thought in SQLite, shows it as a **Thought** card in the UI, and includes it in the trajectory summary.

## Model Tiers and Context Window Sizing

By default, `Ollama` uses a window of `4096` tokens when a client does not send `num_ctx`. That window truncates the front of the chat and drops the system prompt. On the other hand, setting `num_ctx` to `131072` tokens reserves gigabytes of memory for the `KV` cache and slows every step.

Thea defaults `context_tokens` to `32768` (floored at `2048` and clamped to the model's `context_length` reported by `/api/show`). It also sends the same `num_ctx` on both the main turn and the reflection call so that `Ollama` does not unload and reload the model between them.
