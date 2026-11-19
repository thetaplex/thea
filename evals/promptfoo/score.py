"""promptfoo assertions over the scores provider.py returns in `metadata`."""


def _m(context: dict) -> dict:
    return (context.get("providerResponse") or {}).get("metadata") or {}


def _result(ok: bool, reason: str) -> dict:
    return {"pass": ok, "score": 1.0 if ok else 0.0, "reason": reason}


def no_error(output, context):
    err = _m(context).get("error")
    return _result(not err, err or "turn finished")


def citations(output, context):
    """Every [S#] (or [D#] for the Personal Assistant) in the drafts resolves, and there is a draft."""
    return _result(
        bool(_m(context).get("citations_pass")),
        "references resolve"
        if _m(context).get("citations_pass")
        else "a draft is missing or cites an unknown key",
    )


def _check(name: str):
    """An assertion for one of the checks metrics() computed in thea_agent.eval."""

    def run(output, context):
        c = (_m(context).get("checks") or {}).get(name) or {}
        return _result(bool(c.get("pass")), c.get("reason") or "not computed")

    run.__name__ = name
    return run


complete = _check("complete")
deliverable = _check("deliverable")
sources = _check("sources_cited")
honest_report = _check("honest_report")
event = _check("event")
