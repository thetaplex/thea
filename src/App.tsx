import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Code2,
  FileText,
  Folder,
  FolderTree,
  MessageSquare,
  PanelLeft,
  PanelRightClose,
  PanelRightOpen,
  RefreshCw,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { ArtifactPane } from "./components/ArtifactPane";
import { ChatView } from "./components/ChatView";
import { ProjectContextModal } from "./components/ProjectContextModal";
import { SettingsModal, type SettingsTab } from "./components/SettingsModal";
import { Sidebar } from "./components/Sidebar";
import { getProviderMeta } from "./lib/ipc";
import { useAppStore } from "./stores/useAppStore";

export const App: React.FC = () => {
  const {
    initialize,
    providers,
    sessionProvider,
    sessionModel,
    setSessionModel,
    chats,
    selectChat,
    messages,
    models,
    refreshModels,
    selectProject,
    projects,
    projectFiles,
    skills,
    openFileInArtifact,
    leftSidebarOpen,
    setLeftSidebarOpen,
    rightPaneOpen,
    rightPaneTab,
    setRightPaneTab,
    setRightPaneOpen,
    navHistory,
    navIndex,
    goBack,
    goForward,
  } = useAppStore();

  const [showSettings, setShowSettings] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab>("providers");
  const [showProjectContext, setShowProjectContext] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const [modelComboOpen, setModelComboOpen] = useState(false);
  const [refreshingModels, setRefreshingModels] = useState(false);
  const handleRefreshModels = async () => {
    setRefreshingModels(true);
    try {
      await refreshModels();
    } finally {
      setRefreshingModels(false);
    }
  };
  const [modelInput, setModelInput] = useState("");
  const [isTypingModel, setIsTypingModel] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const modelComboRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    initialize();
  }, [initialize]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    const onClickOutside = (e: MouseEvent) => {
      if (modelComboRef.current && !modelComboRef.current.contains(e.target as Node)) {
        setModelComboOpen(false);
        setIsTypingModel(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onClickOutside);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onClickOutside);
    };
  }, []);

  const currentProvider = sessionProvider || "ollama";
  const currentModel = sessionModel || "";
  const getProviderLabel = (provId: string) =>
    providers.find((p) => p.id === provId)?.name || getProviderMeta(provId).label;

  useEffect(() => {
    if (!isTypingModel) {
      setModelInput(currentModel);
    }
  }, [currentModel, isTypingModel]);

  const handleModelChange = async (value: string) => {
    const [prov, ...rest] = value.split("::");
    const modelId = rest.join("::");
    if (!modelId) return;
    await setSessionModel(prov, modelId);
    setModelInput(modelId);
    setIsTypingModel(false);
    setModelComboOpen(false);
  };

  const canGoBack = navIndex > 0;
  const canGoForward = navIndex >= 0 && navIndex < navHistory.length - 1;
  const q = searchQuery.trim().toLowerCase();
  const matchingChats = q ? chats.filter((c) => c.title.toLowerCase().includes(q)).slice(0, 4) : [];
  const matchingMessages = q
    ? messages.filter((m) => m.content?.toLowerCase().includes(q)).slice(0, 4)
    : [];
  const matchingProjects = q
    ? projects
        .filter((p) => p.name.toLowerCase().includes(q) || p.root_path.toLowerCase().includes(q))
        .slice(0, 3)
    : [];
  const matchingFiles = q
    ? projectFiles.filter((f) => !f.is_dir && f.relative_path.toLowerCase().includes(q)).slice(0, 5)
    : [];
  const matchingSkills = q
    ? skills
        .filter((s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q))
        .slice(0, 3)
    : [];
  const hasSearchResults =
    matchingChats.length > 0 ||
    matchingMessages.length > 0 ||
    matchingProjects.length > 0 ||
    matchingFiles.length > 0 ||
    matchingSkills.length > 0;

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-[#faf7f1] text-[#5c4024] antialiased">
      {/* Unified Window Titlebar alongside the macOS red, yellow, green traffic lights (pl-20) */}
      <header
        data-tauri-drag-region
        className="h-11 pl-20 pr-3 flex items-center justify-between gap-3 bg-[#e8decb] shrink-0 select-none"
      >
        {/* Left Navigation Controls right next to red/yellow/green traffic lights */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => setLeftSidebarOpen(!leftSidebarOpen)}
            title={leftSidebarOpen ? "Hide sidebar" : "Show sidebar"}
            className="theta-btn-secondary !px-2 !py-1"
          >
            <PanelLeft className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={goBack}
            disabled={!canGoBack}
            title="Navigate back"
            className="theta-btn-secondary !px-2 !py-1"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={goForward}
            disabled={!canGoForward}
            title="Navigate forward"
            className="theta-btn-secondary !px-2 !py-1"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Center Search Bar in the Window Titlebar */}
        <div className="relative flex-1 max-w-md min-w-[180px]">
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 text-[#8c7358] absolute left-3 pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 180)}
              placeholder="Search chats, messages, files, skills... (⌘K)"
              className="w-full bg-white rounded-lg pl-8 pr-7 py-1 text-xs text-[#4a3219] shadow-2xs"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2 text-[#8c7358] hover:text-[#4a3219]"
                title="Clear search"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {searchFocused && q && (
            <div className="absolute left-0 right-0 top-full mt-1.5 z-50 bg-[#faf7f1] rounded-xl shadow-xl p-2 space-y-2 max-h-80 overflow-y-auto">
              {!hasSearchResults && (
                <div className="px-3 py-2 text-xs text-[#8c7358]">
                  No matches for "{searchQuery}"
                </div>
              )}

              {matchingChats.length > 0 && (
                <div>
                  <div className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#8c7358]">
                    Conversations
                  </div>
                  {matchingChats.map((c) => (
                    <button
                      type="button"
                      key={c.id}
                      onMouseDown={() => {
                        selectChat(c.id);
                        setSearchQuery("");
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-[#4a3219] hover:bg-[#efe7d8] flex items-center gap-2"
                    >
                      <MessageSquare className="w-3.5 h-3.5 text-[#cd8e33] shrink-0" />
                      <span className="truncate">{c.title}</span>
                    </button>
                  ))}
                </div>
              )}

              {matchingMessages.length > 0 && (
                <div>
                  <div className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#8c7358]">
                    Messages in Chat
                  </div>
                  {matchingMessages.map((m) => (
                    <button
                      type="button"
                      key={m.id}
                      onMouseDown={() => {
                        const el = document.getElementById(`msg-${m.id}`);
                        el?.scrollIntoView({
                          behavior: "smooth",
                          block: "center",
                        });
                        setSearchQuery("");
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-[#4a3219] hover:bg-[#efe7d8] truncate"
                    >
                      {m.content.slice(0, 90)}
                    </button>
                  ))}
                </div>
              )}

              {matchingFiles.length > 0 && (
                <div>
                  <div className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#8c7358]">
                    Workspace Files
                  </div>
                  {matchingFiles.map((f) => (
                    <button
                      type="button"
                      key={f.relative_path}
                      onMouseDown={() => {
                        openFileInArtifact(f.relative_path);
                        setSearchQuery("");
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-[#4a3219] hover:bg-[#efe7d8] flex items-center gap-2"
                    >
                      <FileText className="w-3.5 h-3.5 text-[#8b6022] shrink-0" />
                      <span className="truncate font-mono">{f.relative_path}</span>
                    </button>
                  ))}
                </div>
              )}

              {matchingProjects.length > 0 && (
                <div>
                  <div className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#8c7358]">
                    Projects
                  </div>
                  {matchingProjects.map((p) => (
                    <button
                      type="button"
                      key={p.id}
                      onMouseDown={() => {
                        selectProject(p.id);
                        setSearchQuery("");
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-[#4a3219] hover:bg-[#efe7d8] flex items-center gap-2"
                    >
                      <Folder className="w-3.5 h-3.5 text-[#cd8e33] shrink-0" />
                      <span className="truncate">{p.name}</span>
                    </button>
                  ))}
                </div>
              )}

              {matchingSkills.length > 0 && (
                <div>
                  <div className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#8c7358]">
                    Skills
                  </div>
                  {matchingSkills.map((s) => (
                    <button
                      type="button"
                      key={s.name}
                      onMouseDown={() => {
                        setSettingsTab("skills");
                        setShowSettings(true);
                        setSearchQuery("");
                      }}
                      className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-[#4a3219] hover:bg-[#efe7d8] flex items-center gap-2"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-[#cd8e33] shrink-0" />
                      <span className="truncate">{s.name}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Model & Pane Controls in the Window Titlebar */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div
            ref={modelComboRef}
            className="relative flex items-center gap-1 bg-white rounded-lg pl-2 pr-1 py-0.5 shadow-2xs"
          >
            <span className="text-[10px] font-semibold text-[#8b6022] bg-[#f3ece0] px-1.5 py-0.5 rounded shrink-0">
              {getProviderLabel(currentProvider)}
            </span>
            <input
              type="text"
              value={modelInput}
              onFocus={() => {
                setIsTypingModel(false);
                setModelComboOpen(true);
              }}
              onChange={(e) => {
                setModelInput(e.target.value);
                setIsTypingModel(true);
                setModelComboOpen(true);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && modelInput.trim()) {
                  e.preventDefault();
                  handleModelChange(`${currentProvider}::${modelInput.trim()}`);
                }
              }}
              placeholder="Select or type model..."
              className="bg-transparent text-xs text-[#4a3219] font-medium w-36 truncate py-0.5 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => {
                setIsTypingModel(false);
                setModelComboOpen((o) => !o);
              }}
              title="Choose model"
              className="p-1 text-[#70553a] hover:text-[#4a3219] rounded"
            >
              <ChevronDown className="w-3 h-3" />
            </button>
            <button
              type="button"
              onClick={handleRefreshModels}
              disabled={refreshingModels}
              title="Refresh models from active providers"
              className="theta-btn-secondary !p-1"
            >
              <RefreshCw className={`w-3 h-3 ${refreshingModels ? "animate-spin" : ""}`} />
            </button>

            {modelComboOpen && (
              <div className="absolute right-0 top-full mt-1.5 z-50 w-72 max-h-72 overflow-y-auto rounded-xl bg-[#faf7f1] shadow-xl py-1">
                {isTypingModel &&
                  modelInput.trim() &&
                  !models.some((m) => m.id === modelInput.trim()) && (
                    <button
                      type="button"
                      onClick={() => handleModelChange(`${currentProvider}::${modelInput.trim()}`)}
                      className="w-full text-left px-3 py-1.5 text-xs text-[#4a3219] hover:bg-[#efe7d8] flex items-center justify-between"
                    >
                      <span className="truncate font-medium">Use "{modelInput.trim()}"</span>
                      <span className="text-[10px] text-[#8b6022] shrink-0 ml-2">
                        {getProviderLabel(currentProvider)}
                      </span>
                    </button>
                  )}
                {(() => {
                  const activeEntry = providers.find((p) => p.id === currentProvider);
                  const activeMeta = getProviderMeta(currentProvider);
                  const suggested =
                    activeEntry?.models && activeEntry.models.length > 0
                      ? activeEntry.models
                      : activeMeta.suggestedModels;
                  const fallbackEntries = suggested
                    .filter(
                      (id) => !models.some((m) => m.provider === currentProvider && m.id === id),
                    )
                    .map((id) => ({
                      id,
                      name: id,
                      provider: currentProvider,
                      supports_tools: true,
                    }));
                  const combined = [...models, ...fallbackEntries];
                  const filtered =
                    isTypingModel && modelInput.trim()
                      ? combined.filter(
                          (m) =>
                            m.id.toLowerCase().includes(modelInput.trim().toLowerCase()) ||
                            m.name.toLowerCase().includes(modelInput.trim().toLowerCase()),
                        )
                      : combined;
                  if (filtered.length === 0) {
                    return (
                      <div className="px-3 py-2 text-xs text-[#8c7358]">
                        Press Enter to use "{modelInput.trim() || currentModel}"
                      </div>
                    );
                  }
                  return filtered.map((m) => {
                    const isCurrent = m.provider === currentProvider && m.id === currentModel;
                    return (
                      <button
                        key={`${m.provider}::${m.id}`}
                        type="button"
                        onClick={() => handleModelChange(`${m.provider}::${m.id}`)}
                        className={`w-full text-left px-3 py-1.5 text-xs flex items-center justify-between gap-2 transition-colors ${
                          isCurrent
                            ? "bg-[#e3d7c3] text-[#4a3219] font-semibold"
                            : "text-[#5c4024] hover:bg-[#efe7d8]"
                        }`}
                      >
                        <span className="truncate">{m.id}</span>
                        <span className="text-[10px] text-[#8c7358] shrink-0">
                          {getProviderLabel(m.provider)}
                          {m.supports_tools ? " ⚡" : ""}
                        </span>
                      </button>
                    );
                  });
                })()}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setRightPaneOpen(!rightPaneOpen)}
            title={rightPaneOpen ? "Close Artifacts & Files pane" : "Open Artifacts & Files pane"}
            className="theta-btn-secondary !px-2 !py-1"
          >
            {rightPaneOpen ? (
              <PanelRightClose className="w-3.5 h-3.5" />
            ) : (
              <PanelRightOpen className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </header>

      {/* Main 3-pane workspace below the unified window titlebar */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {leftSidebarOpen && (
          <Sidebar
            onOpenSettings={() => {
              setSettingsTab("providers");
              setShowSettings(true);
            }}
            onOpenProjectSettings={() => setShowProjectContext(true)}
          />
        )}

        <ChatView />

        {rightPaneOpen && (
          <aside className="w-[460px] xl:w-[540px] bg-[#f3ece0] flex flex-col h-full shrink-0">
            <div className="h-11 px-3 flex items-center justify-between bg-[#efe7d8]/70">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setRightPaneTab("artifacts")}
                  className={
                    rightPaneTab === "artifacts" ? "theta-btn !py-1" : "theta-btn-secondary !py-1"
                  }
                >
                  <Code2 className="w-3.5 h-3.5" />
                  Artifacts
                </button>
                <button
                  type="button"
                  onClick={() => setRightPaneTab("files")}
                  className={
                    rightPaneTab === "files" ? "theta-btn !py-1" : "theta-btn-secondary !py-1"
                  }
                >
                  <FolderTree className="w-3.5 h-3.5" />
                  Files
                </button>
              </div>
            </div>

            <ArtifactPane mode={rightPaneTab} />
          </aside>
        )}
      </div>

      {showSettings && (
        <SettingsModal initialTab={settingsTab} onClose={() => setShowSettings(false)} />
      )}
      {showProjectContext && <ProjectContextModal onClose={() => setShowProjectContext(false)} />}
    </div>
  );
};

export default App;
