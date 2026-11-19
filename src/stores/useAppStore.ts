import { create } from "zustand";
import {
  type ArtifactItem,
  extractArtifactsFromMarkdown,
  inferLanguageFromPath,
} from "../lib/artifacts";
import {
  type ApprovalDecision,
  type ApprovalRequestPayload,
  type AppSettings,
  api,
  type Chat,
  type FileNode,
  type KnowledgeFile,
  type McpServerConfig,
  type ModelInfo,
  type Persona,
  type Project,
  type ProjectTemplate,
  type ProviderEntry,
  type RoundEvent,
  type SkillInfo,
  type StoredMessage,
  type ToolExecutionEvent,
  type TurnIncompleteEvent,
} from "../lib/ipc";
import { eventInWorkspace, workspaceId } from "../lib/workspace";

export type RightPaneTab = "artifacts" | "files";

interface AppStore {
  settings: AppSettings | null;
  providers: ProviderEntry[];
  sessionProvider: string;
  sessionModel: string;
  personas: Persona[];
  /** The active project's persona; empty in a chat without a project. */
  activePersonaId: string;
  models: ModelInfo[];
  projects: Project[];
  activeProjectId: string | null;
  projectFiles: FileNode[];
  projectFilesError: string | null;
  knowledgeFiles: KnowledgeFile[];
  templates: ProjectTemplate[];

  chats: Chat[];
  activeChatId: string | null;
  messages: StoredMessage[];
  streamingContent: string;
  isStreaming: boolean;
  lastError: string | null;
  incomplete: TurnIncompleteEvent | null;
  round: RoundEvent | null;

  toolEvents: Record<string, ToolExecutionEvent>;
  pendingApprovals: ApprovalRequestPayload[];

  artifacts: ArtifactItem[];
  activeArtifact: ArtifactItem | null;
  leftSidebarOpen: boolean;
  rightPaneOpen: boolean;
  rightPaneTab: RightPaneTab;

  navHistory: Array<{ projectId: string | null; chatId: string | null }>;
  navIndex: number;

  skills: SkillInfo[];
  mcpServers: McpServerConfig[];

  initialize: () => Promise<void>;
  refreshProviders: () => Promise<void>;
  setSessionModel: (provider: string, model: string) => Promise<void>;
  refreshPersonas: () => Promise<void>;
  refreshModels: () => Promise<void>;
  selectProject: (projectId: string | null) => Promise<void>;
  refreshProjectFiles: () => Promise<void>;
  selectChat: (chatId: string | null, fromHistory?: boolean) => Promise<void>;
  goBack: () => Promise<void>;
  goForward: () => Promise<void>;
  createNewChat: (title?: string) => Promise<Chat>;
  sendMessage: (content: string) => Promise<void>;
  stopGeneration: () => Promise<void>;
  decideApproval: (requestId: string, decision: ApprovalDecision) => Promise<void>;

  openFileInArtifact: (relativePath: string) => Promise<void>;
  setActiveArtifact: (item: ArtifactItem | null) => void;
  setLeftSidebarOpen: (open: boolean) => void;
  setRightPaneTab: (tab: RightPaneTab) => void;
  setRightPaneOpen: (open: boolean) => void;

  refreshSkills: () => Promise<void>;
  toggleSkill: (skillName: string, enabled: boolean) => Promise<void>;
  refreshMcpServers: () => Promise<void>;
}

let listenersInitialized = false;
/** Bumped on every project switch: a slower switch must not overwrite a later one. */
let projectSwitch = 0;

/** What the chat pane shows; cleared whenever the chat on screen changes. */
const EMPTY_CHAT_VIEW = {
  messages: [],
  streamingContent: "",
  isStreaming: false,
  lastError: null,
  incomplete: null,
  round: null,
  toolEvents: {},
  artifacts: [],
  activeArtifact: null,
};

/** A project's persona, else the default, else the first; a chat without a project has none. */
function resolvePersonaId(
  personas: Persona[],
  project: Project | null | undefined,
  fallback?: string | null,
): string {
  if (!project) return "";
  if (personas.some((p) => p.id === project.persona_id)) return project.persona_id;
  if (fallback && personas.some((p) => p.id === fallback)) return fallback;
  return personas[0]?.id ?? "";
}

export const useAppStore = create<AppStore>((set, get) => ({
  settings: null,
  providers: [],
  sessionProvider: "ollama",
  sessionModel: "",
  personas: [],
  activePersonaId: "",
  models: [],
  projects: [],
  activeProjectId: null,
  projectFiles: [],
  projectFilesError: null,
  knowledgeFiles: [],
  templates: [],

  chats: [],
  activeChatId: null,
  messages: [],
  streamingContent: "",
  isStreaming: false,
  lastError: null,
  incomplete: null,
  round: null,

  toolEvents: {},
  pendingApprovals: [],

  artifacts: [],
  activeArtifact: null,
  leftSidebarOpen: true,
  rightPaneOpen: true,
  rightPaneTab: "artifacts",

  navHistory: [],
  navIndex: -1,

  skills: [],
  mcpServers: [],

  initialize: async () => {
    try {
      const [settings, providers, personas, projects, templates, mcpServers] = await Promise.all([
        api.getSettings(),
        api.listProviders(),
        api.listPersonas(),
        api.listProjects(),
        api.listTemplates(),
        api.listMcpServers(),
      ]);
      const firstProject = projects[0] ?? null;
      const firstProjectId = firstProject?.id ?? null;
      const initialPersonaId = resolvePersonaId(
        personas,
        firstProject,
        settings?.default_persona_id,
      );
      const chats = await api.listChats(firstProjectId);
      const skills = await api.listSkills(firstProjectId);

      const initialModel = settings?.default_model || "";
      const normalizedSettings = settings;

      set({
        settings: normalizedSettings,
        providers,
        sessionProvider: normalizedSettings?.default_provider || "ollama",
        sessionModel: initialModel,
        personas,
        activePersonaId: initialPersonaId,
        projects,
        templates,
        mcpServers,
        activeProjectId: firstProjectId,
        chats,
        skills,
      });

      if (firstProjectId) {
        await get().refreshProjectFiles();
      }
      if (chats[0]) {
        await get().selectChat(chats[0].id);
      }

      get().refreshModels();

      if (!listenersInitialized) {
        listenersInitialized = true;
        api.onStreamDelta((ev) => {
          if (ev.chat_id === get().activeChatId) {
            set((s) => ({
              streamingContent: s.streamingContent + ev.delta,
              isStreaming: true,
            }));
          }
        });

        api.onToolEvent(async (ev) => {
          set((s) => ({
            toolEvents: { ...s.toolEvents, [ev.tool_call_id]: ev },
            streamingContent: ev.chat_id === s.activeChatId ? "" : s.streamingContent,
          }));
          if (ev.chat_id === get().activeChatId) {
            const msgs = await api.listMessages(ev.chat_id);
            set({ messages: msgs });
          }
          const { activeProjectId, activeChatId, chats } = get();
          if (
            ev.status === "done" &&
            ev.artifact_path &&
            workspaceId(activeProjectId, activeChatId) &&
            eventInWorkspace(
              ev.chat_id,
              activeProjectId,
              activeChatId,
              chats.map((c) => c.id),
            )
          ) {
            get().refreshProjectFiles();
            if (ev.tool_name === "write_file" || ev.tool_name === "edit_file") {
              get().openFileInArtifact(ev.artifact_path);
            }
          }
        });

        api.onApprovalRequest((ev) => {
          set((s) => ({
            pendingApprovals: [...s.pendingApprovals, ev],
          }));
        });

        api.onRound((ev) => {
          if (ev.chat_id === get().activeChatId) set({ round: ev });
        });

        api.onTurnIncomplete((ev) => {
          if (ev.chat_id === get().activeChatId) set({ incomplete: ev });
        });

        api.onTurnFinished(async (ev) => {
          if (ev.chat_id === get().activeChatId) {
            const msgs = await api.listMessages(ev.chat_id);
            const chats = await api.listChats(get().activeProjectId);
            const allArtifacts = collectArtifacts(msgs);
            set((s) => ({
              messages: msgs,
              chats,
              streamingContent: "",
              isStreaming: false,
              toolEvents: {},
              lastError: ev.error ?? null,
              // Files the model wrote this turn were added by openFileInArtifact; keep them.
              artifacts: [...s.artifacts.filter((a) => a.id.startsWith("file:")), ...allArtifacts],
              activeArtifact: s.activeArtifact ?? allArtifacts[allArtifacts.length - 1] ?? null,
            }));
          }
        });
      }
    } catch (err) {
      set({ lastError: String(err) });
    }
  },

  refreshProviders: async () => {
    const providers = await api.listProviders();
    set({ providers });
  },

  setSessionModel: async (provider, model) => {
    set({ sessionProvider: provider, sessionModel: model });
    const currentSettings = get().settings;
    if (currentSettings) {
      const updated = {
        ...currentSettings,
        default_provider: provider,
        default_model: model,
      };
      set({ settings: updated });
      await api.saveSettings(updated);
    }
  },

  refreshPersonas: async () => {
    const personas = await api.listPersonas();
    set({ personas });
  },

  refreshModels: async () => {
    try {
      const models = await api.listProviderModels();
      set({ models });
    } catch {
      // Keep empty list if local server is offline
    }
  },

  selectProject: async (projectId) => {
    const ticket = ++projectSwitch;
    const [chats, skills] = await Promise.all([
      api.listChats(projectId),
      api.listSkills(projectId),
    ]);
    if (ticket !== projectSwitch) return;
    const { projects, personas, settings } = get();
    const proj = projects.find((p) => p.id === projectId);
    const nextPersonaId = resolvePersonaId(personas, proj, settings?.default_persona_id);
    set({
      activeProjectId: projectId,
      activePersonaId: nextPersonaId,
      chats,
      skills,
      ...EMPTY_CHAT_VIEW,
      activeChatId: null,
      projectFiles: [],
      projectFilesError: null,
      knowledgeFiles: [],
    });
    if (projectId) {
      await get().refreshProjectFiles();
    }
    if (chats[0] && ticket === projectSwitch) {
      await get().selectChat(chats[0].id);
    }
  },

  refreshProjectFiles: async () => {
    const { activeProjectId, activeChatId } = get();
    const pid = workspaceId(activeProjectId, activeChatId);
    if (!pid) return;
    // A slower response for a workspace no longer on screen must not overwrite the list.
    const stale = () => workspaceId(get().activeProjectId, get().activeChatId) !== pid;
    try {
      const [projectFiles, knowledgeFiles] = await Promise.all([
        api.listProjectFiles(pid),
        activeProjectId ? api.listKnowledgeFiles(activeProjectId) : Promise.resolve([]),
      ]);
      if (stale()) return;
      set({ projectFiles, knowledgeFiles, projectFilesError: null });
    } catch (err) {
      if (stale()) return;
      set({ projectFiles: [], projectFilesError: String(err) });
    }
  },

  selectChat: async (chatId, fromHistory = false) => {
    if (!chatId) {
      set({ ...EMPTY_CHAT_VIEW, activeChatId: null });
      if (!get().activeProjectId) set({ projectFiles: [], projectFilesError: null });
      return;
    }
    const msgs = await api.listMessages(chatId);
    const allArtifacts = collectArtifacts(msgs);
    set((s) => {
      let nextHistory = s.navHistory;
      let nextIndex = s.navIndex;
      if (!fromHistory) {
        const currentEntry = nextHistory[nextIndex];
        if (
          !currentEntry ||
          currentEntry.chatId !== chatId ||
          currentEntry.projectId !== s.activeProjectId
        ) {
          nextHistory = [
            ...nextHistory.slice(0, nextIndex + 1),
            { projectId: s.activeProjectId, chatId },
          ];
          nextIndex = nextHistory.length - 1;
        }
      }
      return {
        ...EMPTY_CHAT_VIEW,
        activeChatId: chatId,
        messages: msgs,
        artifacts: allArtifacts,
        activeArtifact: allArtifacts[allArtifacts.length - 1] ?? null,
        navHistory: nextHistory,
        navIndex: nextIndex,
      };
    });
    if (!get().activeProjectId) await get().refreshProjectFiles();
  },

  goBack: async () => {
    const { navHistory, navIndex, activeProjectId } = get();
    if (navIndex <= 0) return;
    const targetIndex = navIndex - 1;
    const entry = navHistory[targetIndex];
    if (!entry) return;
    set({ navIndex: targetIndex });
    if (entry.projectId !== activeProjectId) {
      await get().selectProject(entry.projectId);
    }
    await get().selectChat(entry.chatId, true);
  },

  goForward: async () => {
    const { navHistory, navIndex, activeProjectId } = get();
    if (navIndex >= navHistory.length - 1) return;
    const targetIndex = navIndex + 1;
    const entry = navHistory[targetIndex];
    if (!entry) return;
    set({ navIndex: targetIndex });
    if (entry.projectId !== activeProjectId) {
      await get().selectProject(entry.projectId);
    }
    await get().selectChat(entry.chatId, true);
  },

  createNewChat: async (title = "New Chat") => {
    const { activeProjectId, sessionProvider, sessionModel } = get();
    const chat = await api.createChat(
      activeProjectId,
      title,
      sessionProvider || "ollama",
      sessionModel,
    );
    const chats = await api.listChats(activeProjectId);
    set({
      chats,
      activeChatId: chat.id,
      messages: [],
      streamingContent: "",
      artifacts: [],
      activeArtifact: null,
    });
    if (!get().activeProjectId) await get().refreshProjectFiles();
    return chat;
  },

  sendMessage: async (content) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    let chatId = get().activeChatId;
    if (!chatId) {
      const chat = await get().createNewChat(trimmed.slice(0, 40));
      chatId = chat.id;
    }
    set({
      isStreaming: true,
      streamingContent: "",
      lastError: null,
      incomplete: null,
      round: null,
    });
    const userMsg = await api.sendUserMessage(chatId, trimmed);
    set((s) => ({ messages: [...s.messages, userMsg] }));
  },

  stopGeneration: async () => {
    const chatId = get().activeChatId;
    if (!chatId) return;
    await api.stopChatGeneration(chatId);
    set({ isStreaming: false });
  },

  decideApproval: async (requestId, decision) => {
    await api.respondToApproval(requestId, decision);
    set((s) => ({
      pendingApprovals: s.pendingApprovals.filter((p) => p.request_id !== requestId),
    }));
  },

  openFileInArtifact: async (relativePath) => {
    const pid = workspaceId(get().activeProjectId, get().activeChatId);
    if (!pid) return;
    try {
      const content = await api.readProjectFile(pid, relativePath);
      const item: ArtifactItem = {
        id: `file:${relativePath}`,
        title: relativePath,
        language: inferLanguageFromPath(relativePath),
        content,
        sourcePath: relativePath,
      };
      set((s) => ({
        artifacts: [...s.artifacts.filter((a) => a.id !== item.id), item],
        activeArtifact: item,
        rightPaneOpen: true,
        rightPaneTab: "artifacts",
      }));
    } catch (err) {
      set({ lastError: String(err) });
    }
  },

  setActiveArtifact: (item) =>
    set({ activeArtifact: item, rightPaneOpen: true, rightPaneTab: "artifacts" }),

  setLeftSidebarOpen: (open) => set({ leftSidebarOpen: open }),
  setRightPaneTab: (tab) => set({ rightPaneTab: tab, rightPaneOpen: true }),
  setRightPaneOpen: (open) => set({ rightPaneOpen: open }),

  refreshSkills: async () => {
    const skills = await api.listSkills(get().activeProjectId);
    set({ skills });
  },

  toggleSkill: async (skillName, enabled) => {
    await api.toggleSkill(get().activeProjectId, skillName, enabled);
    await get().refreshSkills();
  },

  refreshMcpServers: async () => {
    const mcpServers = await api.listMcpServers();
    set({ mcpServers });
  },
}));

function collectArtifacts(messages: StoredMessage[]): ArtifactItem[] {
  const out: ArtifactItem[] = [];
  for (const m of messages) {
    if (m.role === "assistant") {
      out.push(...extractArtifactsFromMarkdown(m.content, m.id));
    }
  }
  return out;
}
