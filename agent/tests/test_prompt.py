from thea_agent.models import PromptBudget
from thea_agent.prompt import build_system_prompt

BUDGET = PromptBudget.for_tier("small")


def test_prompt_has_persona_and_workspace(turn_req, tmp_path):
    (tmp_path / "notes.md").write_text("x")
    (tmp_path / ".env").write_text("SECRET=1")
    p = build_system_prompt(turn_req(), ["read_file"], BUDGET)
    assert p.startswith("You are Thea, a desktop AI assistant by ThetaPlex")
    assert (
        "## Active Persona: Researcher (Finds things out)\nYou are a careful researcher."
        in p
    )
    assert f"## Active Project: Notes\nWorkspace root: `{tmp_path}`" in p
    assert "### Project Instructions\nKeep it short.\n" in p
    assert "notes.md\n" in p and ".env" not in p
    assert "## Budget\nTool steps this turn: 30.\n" in p
    assert "## How you work" not in p  # no write_file


def test_prompt_how_you_work_and_research_budget(turn_req):
    p = build_system_prompt(turn_req(), ["write_file", "add_source"], BUDGET)
    assert "## How you work" in p and "load_capability" in p and "load_skill" not in p
    assert (
        "web_search returns 5 results. Per round, register and read at most 3 to 5 sources"
        in p
    )


def test_prompt_chat_workspace(turn_req, tmp_path):
    req = turn_req()
    req.workspace.is_chat = True
    p = build_system_prompt(req, [], BUDGET)
    assert (
        f"## Workspace\nThis chat has no project. Its own workspace folder is `{tmp_path}`."
        in p
    )


def test_prompt_pins_knowledge_files_capped(turn_req, tmp_path):
    (tmp_path / "k.md").write_text("a" * 3000 + "TAIL")
    p = build_system_prompt(turn_req(knowledge_files=["k.md"]), [], BUDGET)
    assert (
        "### Pinned Project Knowledge Files\n\n#### File: `k.md`\n```\n"
        + "a" * 2000
        + "\n```\n"
        in p
    )
    assert "TAIL" not in p


def test_prompt_lists_lessons_numbered(turn_req):
    p = build_system_prompt(
        turn_req(lessons=["Cite DOIs", "Read notes first"]), [], BUDGET
    )
    assert p.endswith(
        "\n## Lessons from earlier sessions\n1. Cite DOIs\n2. Read notes first\n"
    )
    assert "Lessons" not in build_system_prompt(turn_req(lessons=[]), [], BUDGET)


def test_plain_chat_prompt_has_no_persona_and_no_checklist(turn_req):
    req = turn_req(persona=None, chat=True)
    p = build_system_prompt(req, ["read_file", "write_file"], BUDGET)
    assert "## Chat\nAnswer the user directly" in p
    assert "save the conversation or a summary" in p
    assert "## Active Persona" not in p
    assert "## How you work" not in p and "TASK.md" not in p
