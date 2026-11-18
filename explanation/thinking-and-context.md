# Thinking Modes and Context Window Sizing

This guide explains why the `Research Assistant` uses `sequential-thinking` and how Thea sizes the context window.

## Why the `Research Assistant` Uses `sequential-thinking`

For the `Research Assistant` persona, Thea sets `native_thinking: false` (which turns off native thinking) and links the `sequential-thinking` `MCP` server instead.

Hidden native thinking tokens have 3 drawbacks on small local models:

- They can run for thousands of tokens without a cap and consume the step budget.
- They are invisible when collapsed or stripped by the provider.
- They leave no messages from tools in SQLite for post-turn reflection.

With the `sequentialthinking` tool and the core system prompt, the model plans in at most `5` short thoughts under `60` words each. It stores every thought in SQLite, shows it as a **Thought** card in the UI, and includes it in the trajectory summary.

## Model Tiers and Context Window Sizing

By default, `Ollama` uses a window of `4096` tokens. That window truncates the front of the chat and drops the system prompt. On the other hand, a window of `131072` tokens reserves gigabytes of memory for the `KV` cache and slows every step.

Thea does not set the window size. It talks to `Ollama` through its `OpenAI`-compatible endpoint, and that endpoint has no field for it. Set `OLLAMA_CONTEXT_LENGTH` on the `Ollama` server instead. A value of `32768` works well with the model tiers. See [Set the Ollama Context Window](../how-to/connect-providers.md#set-the-ollama-context-window) for the steps.
