import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";

export interface Persona {
  id: string;
  name: string;
  tagline: string;
  greeting: string;
  subtitle: string;
  system_prompt: string;
  starter_prompts: string[];
  skill_ids: string[];
  mcp_server_ids: string[];
  tool_ids: string[];
  native_thinking: boolean;
  max_steps: number;
}

export interface ProviderConfig {
  base_url: string;
  api_key: string;
}

export interface ProviderEntry {
  id: string;
  name: string;
  protocol: "ollama" | "openai";
  base_url: string;
  api_key: string;
  enabled: boolean;
  models: string[];
  is_builtin: boolean;
}

export interface ProviderMeta {
  id: string;
  label: string;
  defaultBaseUrl: string;
  apiKeyPlaceholder: string;
  requiresApiKey: boolean;
  suggestedModels: string[];
}

export const PROVIDERS: ProviderMeta[] = [
  {
    id: "ollama",
    label: "Ollama",
    defaultBaseUrl: "http://127.0.0.1:11434",
    apiKeyPlaceholder: "Optional (leave blank for local Ollama)",
    requiresApiKey: false,
    suggestedModels: [
      "qwen3:8b",
      "qwen2.5-coder:7b",
      "llama3.2:latest",
      "deepseek-r1:8b",
      "mistral:latest",
    ],
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    defaultBaseUrl: "https://openrouter.ai/api/v1",
    apiKeyPlaceholder: "sk-or-v1-...",
    requiresApiKey: true,
    suggestedModels: [
      "anthropic/claude-3.7-sonnet",
      "openai/gpt-4o",
      "openai/gpt-4o-mini",
      "google/gemini-2.5-pro",
      "deepseek/deepseek-r1",
      "deepseek/deepseek-chat",
      "qwen/qwen-2.5-coder-32b-instruct",
      "meta-llama/llama-3.3-70b-instruct",
    ],
  },
  {
    id: "openai",
    label: "OpenAI",
    defaultBaseUrl: "https://api.openai.com/v1",
    apiKeyPlaceholder: "sk-...",
    requiresApiKey: true,
    suggestedModels: ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4.1", "gpt-4.1-mini"],
  },
  {
    id: "groq",
    label: "Groq",
    defaultBaseUrl: "https://api.groq.com/openai/v1",
    apiKeyPlaceholder: "gsk_...",
    requiresApiKey: true,
    suggestedModels: [
      "llama-3.3-70b-versatile",
      "deepseek-r1-distill-llama-70b",
      "qwen-qwq-32b",
      "llama-3.1-8b-instant",
    ],
  },
  {
    id: "lmstudio",
    label: "LM Studio",
    defaultBaseUrl: "http://127.0.0.1:1234/v1",
    apiKeyPlaceholder: "Optional (lm-studio)",
    requiresApiKey: false,
    suggestedModels: [
      "qwen2.5-coder-7b-instruct",
      "llama-3.2-3b-instruct",
      "deepseek-r1-distill-qwen-7b",
    ],
  },
  {
    id: "custom",
    label: "Custom (OpenAI-Compatible)",
    defaultBaseUrl: "http://127.0.0.1:1234/v1",
    apiKeyPlaceholder: "Optional Bearer token / API key",
    requiresApiKey: false,
    suggestedModels: [],
  },
];

export const getProviderMeta = (providerId: string): ProviderMeta =>
  PROVIDERS.find((p) => p.id === providerId) || {
    id: providerId,
    label: providerId,
    defaultBaseUrl: "http://127.0.0.1:1234/v1",
    apiKeyPlaceholder: "Optional API key",
    requiresApiKey: false,
    suggestedModels: [],
  };

export interface AppSettings {
  ollama_base_url: string;
  openai_base_url: string;
  openai_api_key: string;
  provider_configs?: Record<string, ProviderConfig>;
  default_provider: string;
  default_model: string;
  default_persona_id: string;
  windows_shell: string;
  mac_shell: string;
  auto_approve_reads: boolean;
  context_tokens: number;
  searxng_url: string;
  small_model?: boolean | null;
}

export interface ModelCapabilities {
  supports_tools: boolean;
  supports_thinking: boolean;
  context_length: number | null;
  parameter_size: string | null;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  size_bytes?: number | null;
  parameter_size?: string | null;
  supports_tools: boolean;
}

export interface Project {
  id: string;
  name: string;
  root_path: string;
  instructions: string;
  persona_id: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeFile {
  id: string;
  project_id: string;
  relative_path: string;
  created_at: string;
}

export interface FileNode {
  name: string;
  relative_path: string;
  is_dir: boolean;
  size: number;
}

export interface ProjectTemplate {
  id: string;
  name: string;
  description: string;
  icon: string;
  default_instructions: string;
  files: Record<string, string>;
}

export interface Chat {
  id: string;
  project_id?: string | null;
  title: string;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface StoredMessage {
  id: string;
  chat_id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  tool_calls_json?: string | null;
  tool_call_id?: string | null;
  tool_name?: string | null;
  created_at: string;
}

export interface SkillInfo {
  name: string;
  description: string;
  body: string;
  source: "builtin" | "global" | "project";
  path: string;
  enabled: boolean;
}

export interface McpServerConfig {
  id: string;
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
  auto_approve: boolean;
}

export interface McpRemoteTool {
  server_id: string;
  server_name: string;
  tool_name: string;
  qualified_name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ApprovalRequestPayload {
  request_id: string;
  chat_id: string;
  project_id: string;
  tool_name: string;
  summary: string;
  details: string;
  diff?: string | null;
}

export interface StreamDeltaEvent {
  chat_id: string;
  delta: string;
}

export interface ToolExecutionEvent {
  chat_id: string;
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "running" | "done" | "rejected" | "error";
  output?: string | null;
  artifact_path?: string | null;
}

export interface TurnFinishedEvent {
  chat_id: string;
  error?: string | null;
}

export interface RoundEvent {
  chat_id: string;
  round: number;
  max_rounds: number;
}

export interface TurnIncompleteEvent {
  chat_id: string;
  reason: string;
  open_items: string[];
}

export type ApprovalDecision = "approve" | "always_allow_project" | "reject";

export const isTauri = (): boolean =>
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export interface Lesson {
  date: string;
  signal: string;
  text: string;
}

export const api = {
  getModelCapabilities: (model: string) =>
    invoke<ModelCapabilities>("get_model_capabilities", { model }),
  getSettings: () => invoke<AppSettings>("get_settings"),
  saveSettings: (settings: AppSettings) => invoke<void>("save_settings", { settings }),

  listProviders: () => invoke<ProviderEntry[]>("list_providers"),
  saveProvider: (provider: ProviderEntry) => invoke<ProviderEntry[]>("save_provider", { provider }),
  deleteProvider: (id: string) => invoke<ProviderEntry[]>("delete_provider", { id }),

  listPersonas: () => invoke<Persona[]>("list_personas"),
  saveCustomPersona: (
    id: string | null,
    name: string,
    tagline: string,
    systemPrompt: string,
    starterPrompts: string[],
    skillIds?: string[],
    mcpServerIds?: string[],
  ) =>
    invoke<Persona>("save_custom_persona", {
      id,
      name,
      tagline,
      systemPrompt,
      starterPrompts,
      skillIds: skillIds ?? [],
      mcpServerIds: mcpServerIds ?? [],
    }),
  deleteCustomPersona: (id: string) => invoke<void>("delete_custom_persona", { id }),

  listProviderModels: () => invoke<ModelInfo[]>("list_provider_models"),
  listModelsForProvider: (provider: string, baseUrl: string, apiKey: string) =>
    invoke<ModelInfo[]>("list_models_for_provider", { provider, baseUrl, apiKey }),
  testProviderConnection: (provider: string, baseUrl: string, apiKey: string) =>
    invoke<ModelInfo[]>("test_provider_connection", { provider, baseUrl, apiKey }),

  listProjects: () => invoke<Project[]>("list_projects"),
  createProject: (
    name: string,
    rootPath: string,
    instructions: string,
    personaId?: string | null,
    templateId?: string | null,
  ) =>
    invoke<Project>("create_project", {
      name,
      rootPath,
      instructions,
      personaId: personaId ?? null,
      templateId: templateId ?? null,
    }),
  updateProject: (id: string, name: string, instructions: string, personaId: string) =>
    invoke<Project>("update_project", { id, name, instructions, personaId }),
  deleteProject: (id: string) => invoke<void>("delete_project", { id }),

  listProjectFiles: (projectId: string, subPath?: string) =>
    invoke<FileNode[]>("list_project_files", { projectId, subPath: subPath ?? null }),
  readProjectFile: (projectId: string, relativePath: string) =>
    invoke<string>("read_project_file", { projectId, relativePath }),
  /** Opens the page in its own window with the print dialog, where the user saves it as PDF. */
  printArtifact: (title: string, html: string) => invoke<void>("print_artifact", { title, html }),
  writeProjectFile: (projectId: string, relativePath: string, content: string) =>
    invoke<string>("write_project_file", { projectId, relativePath, content }),

  listKnowledgeFiles: (projectId: string) =>
    invoke<KnowledgeFile[]>("list_knowledge_files", { projectId }),
  addKnowledgeFile: (projectId: string, relativePath: string) =>
    invoke<KnowledgeFile>("add_knowledge_file", { projectId, relativePath }),
  removeKnowledgeFile: (id: string) => invoke<void>("remove_knowledge_file", { id }),

  listTemplates: () => invoke<ProjectTemplate[]>("list_templates"),

  listChats: (projectId?: string | null) =>
    invoke<Chat[]>("list_chats", { projectId: projectId ?? null }),
  createChat: (projectId: string | null, title: string, provider: string, model: string) =>
    invoke<Chat>("create_chat", { projectId, title, provider, model }),
  deleteChat: (chatId: string) => invoke<void>("delete_chat", { chatId }),

  listMessages: (chatId: string) => invoke<StoredMessage[]>("list_messages", { chatId }),
  sendUserMessage: (chatId: string, content: string) =>
    invoke<StoredMessage>("send_user_message", { chatId, content }),
  stopChatGeneration: (chatId: string) => invoke<void>("stop_chat_generation", { chatId }),

  respondToApproval: (requestId: string, decision: ApprovalDecision) =>
    invoke<boolean>("respond_to_approval", { requestId, decision }),

  listLessons: (personaId: string) => invoke<Lesson[]>("list_lessons", { personaId }),
  updateLesson: (personaId: string, index: number, text: string) =>
    invoke<void>("update_lesson", { personaId, index, text }),
  deleteLesson: (personaId: string, index: number) =>
    invoke<void>("delete_lesson", { personaId, index }),
  rateMessage: (chatId: string, messageId: string, up: boolean, comment?: string) =>
    invoke<void>("rate_message", { chatId, messageId, up, comment: comment ?? null }),

  listSkills: (projectId?: string | null) =>
    invoke<SkillInfo[]>("list_skills", { projectId: projectId ?? null }),
  toggleSkill: (projectId: string | null, skillName: string, enabled: boolean) =>
    invoke<void>("toggle_skill", { projectId, skillName, enabled }),
  createSkill: (
    projectId: string | null,
    scope: "global" | "project",
    name: string,
    description: string,
    body: string,
  ) => invoke<SkillInfo>("create_skill", { projectId, scope, name, description, body }),
  deleteSkill: (projectId: string | null, skillName: string) =>
    invoke<void>("delete_skill", { projectId, skillName }),

  listMcpServers: () => invoke<McpServerConfig[]>("list_mcp_servers"),
  saveMcpServer: (server: McpServerConfig) =>
    invoke<McpServerConfig>("save_mcp_server", { server }),
  deleteMcpServer: (id: string) => invoke<void>("delete_mcp_server", { id }),
  startLmStudioServer: (baseUrl: string) => invoke<void>("start_lmstudio_server", { baseUrl }),
  isCommandAvailable: (name: string) => invoke<boolean>("is_command_available", { name }),
  testMcpServer: (server: McpServerConfig) =>
    invoke<McpRemoteTool[]>("test_mcp_server", { server }),

  pickFolder: async (): Promise<string | null> => {
    if (!isTauri()) return null;
    const selected = await open({ directory: true, multiple: false });
    return typeof selected === "string" ? selected : null;
  },

  onStreamDelta: (cb: (ev: StreamDeltaEvent) => void): Promise<UnlistenFn> =>
    listen<StreamDeltaEvent>("chat:delta", (e) => cb(e.payload)),
  onToolEvent: (cb: (ev: ToolExecutionEvent) => void): Promise<UnlistenFn> =>
    listen<ToolExecutionEvent>("agent:tool-event", (e) => cb(e.payload)),
  onApprovalRequest: (cb: (ev: ApprovalRequestPayload) => void): Promise<UnlistenFn> =>
    listen<ApprovalRequestPayload>("agent:approval-request", (e) => cb(e.payload)),
  onTurnFinished: (cb: (ev: TurnFinishedEvent) => void): Promise<UnlistenFn> =>
    listen<TurnFinishedEvent>("chat:finished", (e) => cb(e.payload)),
  onRound: (cb: (ev: RoundEvent) => void): Promise<UnlistenFn> =>
    listen<RoundEvent>("agent:round", (e) => cb(e.payload)),
  onTurnIncomplete: (cb: (ev: TurnIncompleteEvent) => void): Promise<UnlistenFn> =>
    listen<TurnIncompleteEvent>("agent:incomplete", (e) => cb(e.payload)),
};
