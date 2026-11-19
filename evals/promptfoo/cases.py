"""promptfoo tests from the case files in evals/research/ and evals/assistant/.

A case is {"id", "prompt", "min_sources"?, "persona"?, "seed_files"?}. Its folder is its suite,
so `--filter-metadata suite=research` runs one suite."""

import json
from pathlib import Path

EVALS = Path(__file__).resolve().parents[1]
SUITES = ("research", "assistant")


def generate_tests(config=None) -> list[dict]:
    tests = []
    for suite in SUITES:
        for f in sorted((EVALS / suite).glob("*.json")):
            case = json.loads(f.read_text(encoding="utf-8"))
            tests.append(
                {
                    "description": case["id"],
                    "vars": {**case, "suite": suite},
                    "metadata": {"suite": suite, "case": case["id"]},
                }
            )
    return tests
