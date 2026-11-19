"""Model construction, capability probing and the tier budget."""

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles import merge_profile
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

Tier = Literal["small", "medium", "large"]

_TOOL_FAMILIES = (
    "qwen2.5", "qwen3", "qwen-", "qwen/", "llama3.1", "llama3.2", "llama3.3",
    "llama-3.1", "llama-3.2", "llama-3.3", "mistral", "mixtral", "command-r",
    "firefunction", "hermes", "nemotron", "granite3", "cogito", "gpt-oss", "gpt-4",
    "gpt-5", "o1", "o3", "o4", "claude", "gemini", "devstral", "deepseek-v3",
    "deepseek-chat", "deepseek-r1",
)  # fmt: skip


def guess_supports_tools(model_name: str) -> bool:
    """Heuristic for whether a model family supports native tool calling."""
    lower = model_name.lower()
    return any(f in lower for f in _TOOL_FAMILIES)


@dataclass(frozen=True)
class PromptBudget:
    """Everything that scales with the model: prompt sizes, tool output cap, step cap, research targets."""

    tree_entries: int
    knowledge_chars: int
    tool_output_chars: int
    max_steps: int
    min_sources: int
    max_sources: int
    search_results: int

    @classmethod
    def for_tier(cls, tier: Tier) -> "PromptBudget":
        return _BUDGETS[tier]


_BUDGETS: dict[str, PromptBudget] = {
    "small": PromptBudget(30, 2000, 6000, 30, 3, 5, 5),
    "medium": PromptBudget(45, 4000, 12000, 45, 5, 8, 8),
    "large": PromptBudget(60, 6000, 20000, 60, 8, 12, 10),
}


@dataclass(frozen=True)
class Capabilities:
    supports_tools: bool
    supports_thinking: bool
    context_length: int | None
    params_b: float | None
    tier: Tier


def _tier(params_b: float | None, context_length: int | None) -> Tier:
    """Under 8 B is small, under 20 B medium, the rest large; unknown is medium.
    A context under 16k forces small, under 32k caps at medium."""
    if params_b is None:
        by_params: Tier = "medium"
    else:
        by_params = "small" if params_b < 8 else "medium" if params_b < 20 else "large"
    if context_length is not None:
        if context_length < 16_384:
            return "small"
        if context_length < 32_768 and by_params == "large":
            return "medium"
    return by_params


def _params_b(size: str | None) -> float | None:
    try:
        return float(size.strip().rstrip("Bb")) if size else None
    except ValueError:
        return None


def parse_show_response(model: str, body: dict[str, Any]) -> Capabilities:
    caps = body.get("capabilities")
    caps = caps if isinstance(caps, list) else None
    info = body.get("model_info")
    context_length = None
    if isinstance(info, dict):
        context_length = next(
            (
                v
                for k, v in info.items()
                if k.endswith(".context_length") and isinstance(v, int)
            ),
            None,
        )
    size = (body.get("details") or {}).get("parameter_size")
    params_b = _params_b(size if isinstance(size, str) else None)
    return Capabilities(
        supports_tools="tools" in caps
        if caps is not None
        else guess_supports_tools(model),
        supports_thinking=caps is not None and "thinking" in caps,
        context_length=context_length,
        params_b=params_b,
        tier=_tier(params_b, context_length),
    )


def _ollama_root(base_url: str) -> str:
    return base_url.rstrip("/").removesuffix("/v1")


def _openai_endpoint(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith(("/v1", "/openai")) or "/v1/" in base:
        return f"{base}/{path}"
    return f"{base}/v1/{path}"


def build_model(provider: dict[str, Any], *, thinking: bool = False) -> Model:
    """`thinking`: Ollama reports the model can think. pydantic-ai's name-based profile
    may not know that and would drop the `thinking` setting, so the model keeps its default."""
    if provider["protocol"] == "ollama":
        base = _ollama_root(provider["base_url"]) + "/v1"
        ollama = OllamaProvider(base_url=base, api_key=provider.get("api_key") or None)
        # Ollama's /v1 reads `max_tokens` and ignores `max_completion_tokens`, pydantic-ai's default.
        extra = OpenAIModelProfile(openai_chat_supports_max_completion_tokens=False)
        if thinking:  # thinking=False then sends reasoning_effort "none"
            extra = OpenAIModelProfile(
                openai_chat_supports_max_completion_tokens=False,
                supports_thinking=True,
                openai_supports_reasoning_effort_none=True,
            )
        profile = merge_profile(ollama.model_profile(provider["model"]), extra)
        return OllamaModel(provider["model"], provider=ollama, profile=profile)
    return OpenAIChatModel(
        provider["model"],
        provider=OpenAIProvider(
            base_url=_openai_endpoint(provider["base_url"], "").rstrip("/"),
            api_key=provider.get("api_key") or "none",
        ),
    )


def _client(client: httpx.AsyncClient | None, timeout: float):
    """The caller's client, left open, or a fresh one closed after use."""
    return nullcontext(client) if client else httpx.AsyncClient(timeout=timeout)


async def model_capabilities(
    provider: dict[str, Any], client: httpx.AsyncClient | None = None
) -> Capabilities:
    """`/api/show` for Ollama (heuristic fallback on any failure); OpenAI-compatible servers advertise nothing."""
    if provider["protocol"] != "ollama":
        return Capabilities(True, False, None, None, "medium")
    model = provider["model"]
    # ponytail: no per-model cache; one local /api/show per turn is cheap. Cache if it shows up in latency.
    try:
        async with _client(client, 5) as c:
            r = await c.post(
                f"{_ollama_root(provider['base_url'])}/api/show", json={"model": model}
            )
            r.raise_for_status()
            body = r.json()
    except (httpx.HTTPError, ValueError):
        body = {}
    return parse_show_response(model, body if isinstance(body, dict) else {})


async def test_provider(
    provider: dict[str, Any], client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """`list_models`, plus a key check where `/models` is public and would pass without one."""
    rows = await list_models(provider, client)
    if "openrouter.ai" in provider["base_url"]:
        key = (provider.get("api_key") or "").strip()
        async with _client(client, 8) as c:
            r = await c.get(
                _openai_endpoint(provider["base_url"], "key"),
                headers={"Authorization": f"Bearer {key}"},
            )
        if r.status_code in (401, 403):
            raise ValueError(f"API key rejected: {r.text}")
        r.raise_for_status()
    return rows


async def list_models(
    provider: dict[str, Any], client: httpx.AsyncClient | None = None
) -> list[dict[str, Any]]:
    """Models a provider serves, as `ModelInfo` rows. Connection errors propagate."""
    base = provider["base_url"]
    if provider["protocol"] == "ollama":
        async with _client(client, 5) as c:
            r = await c.get(f"{_ollama_root(base)}/api/tags")
            r.raise_for_status()
            entries = r.json().get("models") or []
        return [
            {
                "id": m["name"],
                "name": m["name"],
                "provider": "ollama",
                "size_bytes": m.get("size"),
                "parameter_size": (m.get("details") or {}).get("parameter_size"),
                "supports_tools": guess_supports_tools(m["name"]),
            }
            for m in entries
        ]
    key = (provider.get("api_key") or "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with _client(client, 8) as c:
        r = await c.get(_openai_endpoint(base, "models"), headers=headers)
        r.raise_for_status()
        data = r.json().get("data") or []
    pid = provider.get("id") or provider["protocol"]
    return [
        {
            "id": m["id"],
            "name": (m.get("name") or "").strip() or m["id"],
            "provider": pid,
            "size_bytes": None,
            "parameter_size": None,
            # OpenAI-compatible servers advertise no capability flag; assume tools.
            "supports_tools": True,
        }
        for m in data
    ]
