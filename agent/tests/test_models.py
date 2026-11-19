import json

import httpx
import pytest
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel

from thea_agent import models
from thea_agent.models import PromptBudget, parse_show_response


def test_parses_capabilities_and_context_length():
    body = {
        "capabilities": ["completion", "tools", "thinking"],
        "details": {"parameter_size": "7.5B"},
        "model_info": {"gemma4.context_length": 131072},
    }
    c = parse_show_response("gemma4:e4b", body)
    assert c.supports_tools and c.supports_thinking
    assert c.context_length == 131072
    assert c.params_b == 7.5
    assert c.tier == "small"


def test_show_response_without_capabilities_falls_back():
    c = parse_show_response("qwen3:8b", {})
    assert c.supports_tools  # heuristic
    assert c.context_length is None
    assert c.tier != "small"


def test_parameter_size_over_8b_is_not_small():
    assert (
        parse_show_response("x", {"details": {"parameter_size": "14B"}}).tier != "small"
    )


def test_tier_follows_params_then_context():
    def t(p: str, ctx: int) -> str:
        body = {
            "details": {"parameter_size": p},
            "model_info": {"m.context_length": ctx},
        }
        return parse_show_response("m", body).tier

    assert t("4B", 131072) == "small"
    assert t("12B", 131072) == "medium"
    assert t("27B", 131072) == "large"
    assert t("27B", 8192) == "small"
    assert t("27B", 20000) == "medium"
    assert parse_show_response("m", {}).tier == "medium"


def test_budget_for_tier_matches_rust():
    s = PromptBudget.for_tier("small")
    assert (s.tree_entries, s.knowledge_chars, s.tool_output_chars, s.max_steps) == (
        30,
        2000,
        6000,
        30,
    )
    assert (s.min_sources, s.max_sources, s.search_results) == (3, 5, 5)
    assert PromptBudget.for_tier("medium").max_steps == 45
    assert PromptBudget.for_tier("large").tool_output_chars == 20000


def test_build_model_appends_v1():
    m = models.build_model(
        {
            "protocol": "ollama",
            "base_url": "http://localhost:11434",
            "api_key": "",
            "model": "gemma4:e4b",
        }
    )
    assert isinstance(m, OllamaModel)
    assert m.base_url.rstrip("/").endswith("/v1")
    assert m.model_name == "gemma4:e4b"
    # Ollama ignores max_completion_tokens: the cap must go as max_tokens, thinking or not.
    assert m.profile.get("openai_chat_supports_max_completion_tokens") is False
    thinking = models.build_model(
        {"protocol": "ollama", "base_url": "http://localhost:11434", "api_key": "", "model": "gemma4:e4b"},
        thinking=True,
    )  # fmt: skip
    assert thinking.profile.get("openai_chat_supports_max_completion_tokens") is False


def test_build_model_openai_compatible():
    m = models.build_model(
        {"protocol": "openai", "base_url": "http://x/v1", "api_key": "", "model": "gpt"}
    )
    assert isinstance(m, OpenAIChatModel)
    assert m.base_url.startswith("http://x/v1")


async def test_model_capabilities_reads_api_show():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"capabilities": ["tools"], "details": {"parameter_size": "27B"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = {
        "protocol": "ollama",
        "base_url": "http://h:11434/v1",
        "api_key": "",
        "model": "m",
    }
    c = await models.model_capabilities(provider, client=client)
    assert seen == {"url": "http://h:11434/api/show", "body": {"model": "m"}}
    assert c.supports_tools and c.tier == "large"


async def test_model_capabilities_falls_back_on_error_and_for_openai():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(500))
    )
    provider = {
        "protocol": "ollama",
        "base_url": "http://h",
        "api_key": "",
        "model": "qwen3:8b",
    }
    c = await models.model_capabilities(provider, client=client)
    assert c.supports_tools and c.tier == "medium"
    oc = await models.model_capabilities(
        {**provider, "protocol": "openai"}, client=client
    )
    assert oc == models.Capabilities(True, False, None, None, "medium")


async def test_list_models_ollama_and_openai():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "qwen3:8b",
                            "size": 5,
                            "details": {"parameter_size": "8B"},
                        }
                    ]
                },
            )
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer k"
        return httpx.Response(
            200, json={"data": [{"id": "gpt-5"}, {"id": "a", "name": "A"}]}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    ollama = await models.list_models(
        {"protocol": "ollama", "base_url": "http://h", "api_key": ""}, client=client
    )
    assert ollama == [
        {
            "id": "qwen3:8b",
            "name": "qwen3:8b",
            "provider": "ollama",
            "size_bytes": 5,
            "parameter_size": "8B",
            "supports_tools": True,
        }
    ]
    oa = await models.list_models(
        {
            "id": "lmstudio",
            "protocol": "openai",
            "base_url": "http://h",
            "api_key": "k",
        },
        client=client,
    )
    assert [(m["id"], m["name"], m["provider"], m["supports_tools"]) for m in oa] == [
        ("gpt-5", "gpt-5", "lmstudio", True),
        ("a", "A", "lmstudio", True),
    ]


def test_build_model_openai_bare_host_gets_v1():
    m = models.build_model(
        {
            "protocol": "openai",
            "base_url": "http://localhost:1234",
            "api_key": "",
            "model": "x",
        }
    )
    assert m.base_url.rstrip("/") == "http://localhost:1234/v1"


async def test_thinking_off_reaches_ollama():
    """pydantic-ai's profile for gemma4 says no thinking, so `thinking: False` was dropped and gemma4 thought anyway."""
    import json

    import httpx
    from pydantic_ai import Agent

    bodies = []

    def handler(req: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(req.content))
        msg = {"role": "assistant", "content": "hi"}
        return httpx.Response(
            200,
            json={"id": "1", "object": "chat.completion", "created": 0, "model": "m",
                  "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}]},
        )  # fmt: skip

    provider = {
        "protocol": "ollama",
        "base_url": "http://x:11434",
        "model": "gemma4:e4b",
    }
    for thinking, want in ((True, "none"), (False, None)):
        m = models.build_model(provider, thinking=thinking)
        m.client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        await Agent(m).run("hi", model_settings={"thinking": False})
        assert bodies[-1].get("reasoning_effort") == want


async def test_test_provider_checks_openrouter_key():
    """OpenRouter's /models is public, so Test passed with no key and every turn then 401'd."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json={"data": [{"id": "a/b"}]})
        assert request.url.path == "/api/v1/key"
        ok = request.headers["authorization"] == "Bearer sk-or-good"
        return httpx.Response(200 if ok else 401, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    base = {"protocol": "openai", "base_url": "https://openrouter.ai/api/v1"}
    rows = await models.test_provider({**base, "api_key": "sk-or-good"}, client=client)
    assert [m["id"] for m in rows] == ["a/b"]
    with pytest.raises(ValueError, match="API key rejected"):
        await models.test_provider({**base, "api_key": ""}, client=client)
