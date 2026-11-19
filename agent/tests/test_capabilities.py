from pathlib import Path

from conftest import allow_all
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import LocalWorkspace
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryFeedbackPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import UsageLimits
from pydantic_ai_harness import FileSystem

from thea_agent import capabilities as caps
from thea_agent.capabilities import (
    EDIT_NEEDS_OLD_TEXT,
    EMPTY_REPLY_NUDGE,
    MAX_NUDGES,
    MAX_THOUGHTS,
    NOT_STARTED_NUDGE,
    THOUGHT_LIMIT,
    WRAP_UP,
    EditFile,
    ThoughtCap,
    ToolErrors,
    WrapUpNearRequestLimit,
    nudge_for,
    nudge_for_reply,
    open_items,
    reset_finished_task,
)
from thea_agent.deps import TurnDeps

# --- ported from task.rs ---------------------------------------------------


def test_no_checklist_is_not_started(tmp_path: Path):
    assert nudge_for_reply(tmp_path, "Here is a plan.") == NOT_STARTED_NUDGE
    (tmp_path / "TASK.md").write_text("")
    assert nudge_for_reply(tmp_path, "Here is a plan.") == NOT_STARTED_NUDGE


def test_open_items_are_in_progress(tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [x] one\n- [ ] two\n")
    assert "still has open items:\n- [ ] two" in nudge_for_reply(tmp_path, "done")


def test_a_question_to_the_user_ends_the_turn(tmp_path: Path):
    (tmp_path / "TASK.md").write_text(
        "- [x] one\n- [ ] Ask the user: which city?\n- [ ] two\n"
    )
    assert nudge_for_reply(tmp_path, "Which city?") is None


def test_all_done_is_finished(tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [x] one\n- [!] two: no source\n")
    assert nudge_for_reply(tmp_path, "Here is the answer.") is None
    assert nudge_for_reply(tmp_path, "  \n") == EMPTY_REPLY_NUDGE


def test_no_workspace_keeps_the_reply():
    assert nudge_for_reply(None, "hi") is None


def test_a_finished_checklist_is_emptied_at_the_start_of_a_turn(tmp_path: Path):
    reset_finished_task(tmp_path)  # no file: nothing happens
    assert not (tmp_path / "TASK.md").exists()
    task = tmp_path / "TASK.md"
    task.write_text("- [x] one\n- [!] two\n")
    reset_finished_task(tmp_path)
    assert task.read_text() == ""
    task.write_text("- [x] one\n- [ ] Ask the user: which city?\n")
    reset_finished_task(tmp_path)
    assert "Ask the user" in task.read_text()


def test_open_items_finds_unchecked_lines_only():
    md = "# Task\nGoal\n\n## Done when\n- [ ] Draft at research/drafts/a.md\n- [x] Sources registered\n  - [ ] indented counts\n- [X] upper done\n- not a box\n"
    assert open_items(md) == [
        "- [ ] Draft at research/drafts/a.md",
        "- [ ] indented counts",
    ]


def test_nudge_only_when_file_has_open_items(tmp_path: Path):
    assert nudge_for(tmp_path) is None
    (tmp_path / "TASK.md").write_text("- [x] done\n")
    assert nudge_for(tmp_path) is None
    (tmp_path / "TASK.md").write_text("- [ ] one\n- [ ] two\n")
    assert nudge_for(tmp_path) == (
        "TASK.md still has open items:\n- [ ] one\n- [ ] two\n"
        "Do the next one now. Tick it with edit_file when its proof has run."
    )


# --- agent runs with FunctionModel ------------------------------------------


def _deps(root: Path | None) -> TurnDeps:
    return TurnDeps(
        root=root,
        emit=lambda n, p: None,
        chat_id="c1",
        approvals=allow_all(),
        checklist=True,
    )


def _parts(messages: list[ModelMessage], kind) -> list:
    return [p for m in messages for p in m.parts if isinstance(p, kind)]


def _agent(fn, *, tools=(), capabilities=()) -> Agent:
    agent = Agent(
        FunctionModel(fn),
        deps_type=TurnDeps,
        tools=list(tools),
        capabilities=list(capabilities),
        retries={"output": MAX_NUDGES},
    )
    agent.output_validator(caps.task_nudge)
    return agent


async def tick(ctx: RunContext[TurnDeps]) -> str:
    """Tick every TASK.md item."""
    p = ctx.deps.root / "TASK.md"
    p.write_text(p.read_text().replace("- [ ]", "- [x]"))
    return "Wrote TASK.md"


async def noop() -> str:
    """Do nothing."""
    return "ok"


async def test_task_nudge_retries_until_items_ticked(tmp_path: Path):
    (tmp_path / "TASK.md").write_text("# Task\n- [ ] one\n")
    seen: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # The model sees retry feedback as a user prompt wrapping the nudge text.
        last = " ".join(str(getattr(p, "content", "")) for p in messages[-1].parts)
        if "still has open items" in last:
            seen.append(last)
        retries = seen
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("noop", {})])
        if not retries:
            return ModelResponse(parts=[TextPart("done")])
        if _parts(messages, ToolReturnPart)[-1].tool_name != "tick":
            return ModelResponse(parts=[ToolCallPart("tick", {})])
        return ModelResponse(parts=[TextPart("all ticked")])

    result = await _agent(model, tools=[noop, tick]).run("go", deps=_deps(tmp_path))
    assert result.output == "all ticked"
    assert "- [x] one" in (tmp_path / "TASK.md").read_text()
    assert len(seen) == 1 and "TASK.md still has open items:\n- [ ] one" in seen[0]


async def test_task_nudge_gives_up_after_max_nudges(tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [ ] never\n")
    calls = 0

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("noop", {})])
        return ModelResponse(parts=[TextPart("stuck")])

    result = await _agent(model, tools=[noop]).run("go", deps=_deps(tmp_path))
    assert result.output == "stuck"
    assert len(_parts(result.all_messages(), RetryFeedbackPart)) == MAX_NUDGES
    assert calls == 2 + MAX_NUDGES


async def test_a_text_plan_before_any_tool_is_nudged(tmp_path: Path):
    """brief-heat-pumps: the first reply was a plan as text, with no TASK.md, and the turn ended."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[TextPart("Thought 1: load deep-research.")])
        (tmp_path / "TASK.md").write_text("- [x] one\n")
        return ModelResponse(parts=[TextPart("done")])

    result = await _agent(model, tools=[noop]).run("brief", deps=_deps(tmp_path))
    assert result.output == "done"
    [nudge] = _parts(result.all_messages(), RetryFeedbackPart)
    assert NOT_STARTED_NUDGE in str(nudge.content)


async def test_not_started_is_nudged_once(tmp_path: Path):
    """A direct answer in a project ("thanks") costs one nudge, then stands."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("You are welcome.")])

    result = await _agent(model, tools=[noop]).run("thanks", deps=_deps(tmp_path))
    assert result.output == "You are welcome."
    assert len(_parts(result.all_messages(), RetryFeedbackPart)) == 1


async def test_plain_chat_reply_stands(tmp_path: Path):
    deps = _deps(tmp_path)
    deps.checklist = False

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("hi")])

    result = await _agent(model, tools=[noop]).run("hi", deps=deps)
    assert not _parts(result.all_messages(), RetryFeedbackPart)


async def test_wrap_up_on_last_request(tmp_path: Path):
    seen: list[tuple[list[str], bool]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        wrap = any(WRAP_UP in str(p.content) for p in messages[-1].parts)
        seen.append(([t.name for t in info.function_tools], wrap))
        if info.function_tools:
            return ModelResponse(parts=[ToolCallPart("noop", {})])
        return ModelResponse(parts=[TextPart("status")])

    agent = _agent(model, tools=[noop], capabilities=[WrapUpNearRequestLimit()])
    result = await agent.run(
        "go", deps=_deps(None), usage_limits=UsageLimits(request_limit=3)
    )
    assert result.output == "status"
    assert seen == [(["noop"], False), (["noop"], False), ([], True)]


async def test_thought_cap_answers_extra_thoughts(tmp_path: Path):
    # Past the cap the model keeps calling the tool, even with bad args: the turn goes on.
    ran: list[str] = []

    async def mcp__seq__sequentialthinking(thought: str) -> str:
        """Think."""
        ran.append(thought)
        return "ok"

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert "mcp__seq__sequentialthinking" in [t.name for t in info.function_tools]
        n = sum(isinstance(m, ModelResponse) for m in messages)
        if n < MAX_THOUGHTS + 3:
            args = {"thought": "t"} if n < MAX_THOUGHTS else {"bad": 1}
            return ModelResponse(
                parts=[ToolCallPart("mcp__seq__sequentialthinking", args)]
            )
        return ModelResponse(parts=[TextPart("plan made")])

    agent = _agent(
        model, tools=[mcp__seq__sequentialthinking, noop], capabilities=[ThoughtCap()]
    )
    result = await agent.run("go", deps=_deps(None))
    assert result.output == "plan made"
    assert len(ran) == MAX_THOUGHTS
    rets = _parts(result.all_messages(), ToolReturnPart)
    assert [r.content for r in rets[MAX_THOUGHTS:]] == [THOUGHT_LIMIT] * 3
    assert not _parts(result.all_messages(), RetryFeedbackPart)


async def test_edit_file_needs_old_text(tmp_path: Path):
    # A model that wants a full rewrite is told to use write_file, and the file is untouched.
    (tmp_path / "draft.md").write_text("TODO\n")
    seen: list[dict] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        [edit] = [t for t in info.function_tools if t.name == "edit_file"]
        seen.append(edit.parameters_json_schema)
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "edit_file", {"path": "draft.md", "new_text": "Full\n"}
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("done")])

    agent = Agent(
        FunctionModel(model),
        deps_type=TurnDeps,
        capabilities=[
            LocalWorkspace(tmp_path),
            FileSystem(tools=("read_file", "write_file", "edit_file")),
            EditFile(),
        ],
    )
    result = await agent.run("go", deps=_deps(tmp_path))
    assert result.output == "done"
    assert seen[0]["required"] == ["path", "old_text", "new_text"]
    assert "replacements" not in seen[0]["properties"]
    [ret] = _parts(result.all_messages(), ToolReturnPart)
    assert ret.outcome == "retried" and EDIT_NEEDS_OLD_TEXT in str(ret.content)
    assert (tmp_path / "draft.md").read_text() == "TODO\n"


async def test_oserror_becomes_failed_result(tmp_path: Path):
    async def broken() -> str:
        """Read a file that is not there."""
        raise FileNotFoundError("no such file: x.md")

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("broken", {})])
        return ModelResponse(parts=[TextPart("recovered")])

    agent = _agent(model, tools=[broken], capabilities=[ToolErrors()])
    result = await agent.run("go", deps=_deps(None))
    assert result.output == "recovered"
    [ret] = _parts(result.all_messages(), ToolReturnPart)
    assert ret.outcome == "failed" and "no such file: x.md" in str(ret.content)


async def test_wrap_up_is_not_nudged_with_open_items(tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [ ] open\n")

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if info.function_tools:
            return ModelResponse(parts=[ToolCallPart("noop", {})])
        return ModelResponse(parts=[TextPart("status")])

    agent = _agent(model, tools=[noop], capabilities=[WrapUpNearRequestLimit()])
    result = await agent.run(
        "go", deps=_deps(tmp_path), usage_limits=UsageLimits(request_limit=3)
    )
    assert result.output == "status"


async def test_penultimate_reply_is_nudged_into_wrap_up(tmp_path: Path):
    (tmp_path / "TASK.md").write_text("- [ ] open\n")
    replies: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("noop", {})])
        last = " ".join(str(getattr(p, "content", "")) for p in messages[-1].parts)
        if WRAP_UP in last:
            assert not info.function_tools
            assert (
                "still has open items" in last
            )  # the nudge and the wrap-up arrive together
            replies.append("status")
        else:
            replies.append("early")
        return ModelResponse(parts=[TextPart(replies[-1])])

    agent = _agent(model, tools=[noop], capabilities=[WrapUpNearRequestLimit()])
    result = await agent.run(
        "go", deps=_deps(tmp_path), usage_limits=UsageLimits(request_limit=3)
    )
    assert replies == ["early", "status"]
    assert result.output == "status"


async def test_a_question_asked_with_ask_user_ends_the_turn(tmp_path: Path):
    """book-research intake: the open item said "Ask the author ...", not "Ask the user", so the
    questions were nudged and the model guessed the answers instead of waiting."""
    (tmp_path / "TASK.md").write_text(
        "- [x] Load book-research\n- [ ] Ask the author intake questions\n"
    )

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("ask_user", {"questions": "1. Fiction?"})]
            )
        return ModelResponse(parts=[TextPart("1. Fiction or non-fiction?")])

    deps = _deps(tmp_path)
    result = await _agent(model, tools=[caps.ask_user]).run("research", deps=deps)
    assert result.output == "1. Fiction or non-fiction?"
    assert not _parts(result.all_messages(), RetryFeedbackPart)
    assert deps.asked
