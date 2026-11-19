"""JSON-lines wire protocol between the Rust host and the sidecar."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class Persona(BaseModel):
    id: str
    name: str
    tagline: str
    system_prompt: str
    tool_ids: list[str]
    skill_ids: list[str]
    mcp_server_ids: list[str]
    builtin: bool
    native_thinking: bool
    max_steps: int


class Provider(BaseModel):
    protocol: str
    base_url: str
    api_key: str
    model: str


class Workspace(BaseModel):
    id: str
    name: str
    root_path: str
    instructions: str
    is_chat: bool


class McpServer(BaseModel):
    id: str
    name: str
    command: str
    args: list[str]
    env: dict[str, str]
    enabled: bool
    auto_approve: bool


class StoredRow(BaseModel):
    role: str
    content: str
    tool_calls_json: str | None
    tool_call_id: str | None
    tool_name: str | None
    model_message_json: str | None


class TurnRequest(BaseModel):
    type: Literal["turn"]
    chat_id: str
    persona: Persona | None  # None: a chat without a project, a plain chat
    provider: Provider
    small_model: bool | None
    workspace: Workspace | None
    knowledge_files: list[str]
    skill_dirs: list[str]
    skills: list[str]
    mcp_servers: list[McpServer]
    settings: dict[str, Any]
    lessons: list[str]
    history: list[StoredRow]


class Approval(BaseModel):
    type: Literal["approval"]
    request_id: str
    decision: Literal["approve", "always_allow_project", "reject"]


class Cancel(BaseModel):
    type: Literal["cancel"]
    chat_id: str


class Call(BaseModel):
    type: Literal["call"]
    id: str
    method: str
    params: dict[str, Any] = {}


class Event(BaseModel):
    type: Literal["event"]
    name: str
    payload: dict[str, Any]


class Result(BaseModel):
    type: Literal["result"]
    id: str
    ok: bool
    value: Any = None
    error: str | None = None


Incoming = Annotated[
    TurnRequest | Approval | Cancel | Call, Field(discriminator="type")
]
