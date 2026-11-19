"""promptfoo provider: runs one case headless through `thea_agent.eval` and scores it.

The case's prompt is the user message; `vars` may set any other `Case` field. The scores go back as `metadata`, which score.py turns into assertions.
Each case's transcript and first prompt land in evals/results/promptfoo/<suite>-<model>-<date>/.
"""

import asyncio
from datetime import date
from pathlib import Path

from thea_agent import eval as ev

REPO = Path(__file__).resolve().parents[2]


def call_api(prompt: str, options: dict, context: dict) -> dict:
    v = context.get("vars") or {}
    cfg = options.get("config") or {}
    # Every Case field the case file sets: a hand-kept list once dropped `deliverable` and `event`.
    case = ev.Case(prompt=prompt, **{k: v[k] for k in ev.Case.model_fields if k in v and k != "prompt"})
    o = asyncio.run(
        ev.run_case(case, cfg["model"], cfg.get("base_url") or "http://127.0.0.1:11434")
    )
    suite = f"{ev.sanitize(v.get('suite', 'eval'))}-{ev.sanitize(cfg['model'])}-{date.today()}"
    ev.write_transcript(REPO / "evals/results/promptfoo" / suite, case.id, o)
    answer = next(
        (
            m["content"]
            for m in reversed(o.messages)
            if m["role"] == "assistant" and m["content"]
        ),
        "",
    )
    return {"output": answer, "metadata": ev.metrics(case, o)}
