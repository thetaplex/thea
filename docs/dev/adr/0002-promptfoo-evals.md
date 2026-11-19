# 2. Run the Evaluations with `promptfoo`

Date: 2026-11-17

## Status

Accepted. Changes [ADR 0001](0001-python-agent-sidecar.md): `pydantic-evals` is no longer a dependency.

## Context

The first port of the evaluation used `pydantic-evals`. It ran the cases, scored each draft, and wrote one `JSON` report. It had no viewer, and it could not compare one run with another. Its pass and fail used only the citation check and the source count. A turn that stopped on an error still passed when a draft was on disk.

`promptfoo` runs cases, gives each check a result, keeps a history of runs, and has a viewer that compares runs and models.

## Decision

`promptfoo` runs the evaluations. `evals/promptfoo/provider.py` runs one case through `thea_agent.eval`, which keeps the case setup, the headless approvals, and the scores. `evals/promptfoo/score.py` turns the scores into checks of what the user gets: `no_error`, `complete`, `deliverable`, `citations`, `sources`, `style`, `honest_report`, and `event`.

`just eval [model] [suite]` runs one suite. We pin `promptfoo` to an exact version, as we do for the Python libraries.

## Consequences

- A turn that stops on an error fails the `no_error` check.
- The evaluation needs `npx` (`Node.js`), which the `MCP` servers need already.
- `npx promptfoo view` shows the runs and compares them.
- The case files in `evals/research/` and `evals/assistant/` do not change.
