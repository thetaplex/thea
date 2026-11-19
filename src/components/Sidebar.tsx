import {
  BookOpen,
  ChevronRight,
  FolderOpen,
  FolderPlus,
  Layers,
  MessageSquarePlus,
  Settings,
  Trash2,
  UserPlus,
} from "lucide-react";
import type React from "react";
import { useState } from "react";
import { api } from "../lib/ipc";
import { templatesFor } from "../lib/workspace";
import { useAppStore } from "../stores/useAppStore";

interface SidebarProps {
  onOpenSettings: () => void;
  onOpenProjectSettings: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ onOpenSettings, onOpenProjectSettings }) => {
  const {
    projects,
    activeProjectId,
    selectProject,
    personas,
    refreshPersonas,
    chats,
    activeChatId,
    selectChat,
    createNewChat,
    templates,
    skills,
    mcpServers,
    initialize,
  } = useAppStore();

  const [showNewProject, setShowNewProject] = useState(false);
  const [projName, setProjName] = useState("");
  const [projPath, setProjPath] = useState("");
  const [selectedPersonaId, setSelectedPersonaId] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("empty");
  const [projInstructions, setProjInstructions] = useState("");
  const [creatingError, setCreatingError] = useState<string | null>(null);

  const [showNewPersona, setShowNewPersona] = useState(false);
  const [personaName, setPersonaName] = useState("");
  const [personaTagline, setPersonaTagline] = useState("");
  const [personaPrompt, setPersonaPrompt] = useState("");
  const [personaStarters, setPersonaStarters] = useState("");
  const [personaSkillIds, setPersonaSkillIds] = useState<string[]>([]);
  const [personaMcpIds, setPersonaMcpIds] = useState<string[]>([]);
  const [personaError, setPersonaError] = useState<string | null>(null);

  const shownTemplates = templatesFor(selectedPersonaId, templates);
  const choosePersona = (id: string) => {
    setSelectedPersonaId(id);
    // A code template picked for another persona is not on offer for this one.
    if (selectedTemplate && !templatesFor(id, templates).some((t) => t.id === selectedTemplate)) {
      setSelectedTemplate("empty");
    }
  };

  const handlePickFolder = async () => {
    const picked = await api.pickFolder();
    if (picked) {
      setProjPath(picked);
      if (!projName) {
        const parts = picked.replace(/\\/g, "/").split("/").filter(Boolean);
        setProjName(parts[parts.length - 1] || "Research Project");
      }
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingError(null);
    if (!projName.trim() || !projPath.trim()) {
      setCreatingError("Please enter both a project name and workspace folder path.");
      return;
    }
    try {
      const created = await api.createProject(
        projName.trim(),
        projPath.trim(),
        projInstructions,
        selectedPersonaId,
        selectedTemplate || null,
      );
      setShowNewProject(false);
      setProjName("");
      setProjPath("");
      setProjInstructions("");
      await initialize();
      await selectProject(created.id);
    } catch (err) {
      setCreatingError(String(err));
    }
  };

  const handleCreatePersona = async (e: React.FormEvent) => {
    e.preventDefault();
    setPersonaError(null);
    if (!personaName.trim() || !personaPrompt.trim()) {
      setPersonaError("Please enter a persona name and system instructions.");
      return;
    }
    try {
      const starters = personaStarters
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const created = await api.saveCustomPersona(
        null,
        personaName.trim(),
        personaTagline.trim() || "Custom assistant persona",
        personaPrompt.trim(),
        starters,
        personaSkillIds,
        personaMcpIds,
      );
      setShowNewPersona(false);
      setPersonaName("");
      setPersonaTagline("");
      setPersonaPrompt("");
      setPersonaStarters("");
      setPersonaSkillIds([]);
      setPersonaMcpIds([]);
      await refreshPersonas();
      choosePersona(created.id);
    } catch (err) {
      setPersonaError(String(err));
    }
  };

  const handleDeleteChat = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await api.deleteChat(id);
    const updated = await api.listChats(activeProjectId);
    useAppStore.setState({ chats: updated });
    if (activeChatId === id) {
      await selectChat(updated[0]?.id ?? null);
    }
  };

  return (
    <aside className="w-72 bg-[#efe7d8] flex flex-col h-full select-none shrink-0">
      {/* Projects section: a persona belongs to a project */}
      <div className="p-3.5 bg-[#e8decb]/35 space-y-2.5">
        {/* Projects list */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[#8c7358]">
              Projects
            </span>
            <button
              type="button"
              onClick={() => {
                choosePersona(personas[0]?.id || "");
                setShowNewProject(true);
              }}
              className="theta-btn !px-2.5 !py-1"
            >
              <FolderPlus className="w-3.5 h-3.5" />
              New
            </button>
          </div>

          <div className="max-h-40 overflow-y-auto space-y-1">
            {projects.map((p) => {
              const active = p.id === activeProjectId;
              const toggle = () => selectProject(active ? null : p.id);
              return (
                // biome-ignore lint/a11y/useSemanticElements: contains a nested context button, so cannot itself be a <button>
                <div
                  key={p.id}
                  role="button"
                  tabIndex={0}
                  onClick={toggle}
                  onKeyDown={(e) => e.key === "Enter" && toggle()}
                  className={`group flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition ${
                    active
                      ? "bg-white text-[#4a3219] shadow-xs"
                      : "text-[#5c4024] hover:bg-[#e8decb]/70"
                  }`}
                >
                  <div className="truncate pr-2">
                    <div className="font-medium truncate">{p.name}</div>
                    <div className="text-[10px] text-[#8c7358] truncate" title={p.root_path}>
                      {p.root_path}
                    </div>
                  </div>
                  {active && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenProjectSettings();
                      }}
                      className="theta-btn-secondary !px-2 !py-0.5 shrink-0"
                      title="Project context"
                    >
                      <BookOpen className="w-3 h-3" />
                      Context
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Chats list */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-1.5">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-[#8c7358]">
            Conversations
          </span>
          <button type="button" onClick={() => createNewChat()} className="theta-btn !px-2.5 !py-1">
            <MessageSquarePlus className="w-3.5 h-3.5" />
            New
          </button>
        </div>

        {chats.length === 0 ? (
          <div className="text-xs text-[#8c7358] py-6 text-center">
            No conversations yet. Start chatting below!
          </div>
        ) : (
          chats.map((c) => {
            const active = c.id === activeChatId;
            return (
              // biome-ignore lint/a11y/useSemanticElements: contains a nested delete button, so cannot itself be a <button>
              <div
                key={c.id}
                role="button"
                tabIndex={0}
                onClick={() => selectChat(c.id)}
                onKeyDown={(e) => e.key === "Enter" && selectChat(c.id)}
                className={`group flex items-center justify-between px-3 py-2 rounded-lg text-xs cursor-pointer transition ${
                  active
                    ? "bg-white text-[#4a3219] shadow-xs"
                    : "text-[#5c4024] hover:bg-[#e8decb]/70"
                }`}
              >
                <div className="truncate pr-2">
                  <div className="font-medium truncate">{c.title}</div>
                </div>
                <button
                  type="button"
                  onClick={(e) => handleDeleteChat(e, c.id)}
                  className="opacity-0 group-hover:opacity-100 theta-btn-secondary !p-1"
                  title="Delete chat"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>

      {/* Bottom action: Settings */}
      <div className="p-3.5 bg-[#e8decb]/50">
        <button
          type="button"
          onClick={onOpenSettings}
          className="theta-btn-secondary w-full !justify-between !bg-white shadow-2xs"
        >
          <span className="flex items-center gap-2 font-medium">
            <Settings className="w-3.5 h-3.5 text-[#8b6022]" />
            <span>Settings</span>
          </span>
          <ChevronRight className="w-3.5 h-3.5 text-[#8c7358]" />
        </button>
      </div>

      {/* New Project Modal */}
      {showNewProject && (
        <div className="fixed inset-0 z-50 bg-[#4a3219]/45 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="theta-card max-w-lg w-full p-6 shadow-2xl max-h-[92vh] overflow-y-auto">
            <div className="flex items-center gap-2 mb-4">
              <Layers className="w-5 h-5 text-[#cd8e33]" />
              <h2 className="font-display text-2xl font-semibold text-[#4a3219]">
                Create or Open Project
              </h2>
            </div>

            <form onSubmit={handleCreateProject} className="space-y-3.5 text-xs">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label htmlFor="assistant-persona" className="block text-[#4a3219] font-medium">
                    Assistant Persona
                  </label>
                  <button
                    type="button"
                    onClick={() => setShowNewPersona(true)}
                    className="theta-btn !px-2.5 !py-1"
                  >
                    <UserPlus className="w-3.5 h-3.5" />
                    New persona
                  </button>
                </div>
                <select
                  id="assistant-persona"
                  value={selectedPersonaId}
                  onChange={(e) => choosePersona(e.target.value)}
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                >
                  {personas.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} — {p.tagline}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <div className="block text-[#4a3219] font-medium mb-1.5">Project Template</div>
                <div className="grid grid-cols-2 gap-2">
                  {shownTemplates.map((t) => (
                    <button
                      type="button"
                      key={t.id}
                      onClick={() => setSelectedTemplate(t.id)}
                      className={`text-left p-3 rounded-lg transition ${
                        selectedTemplate === t.id
                          ? "bg-[#efe7d8] ring-2 ring-[#cd8e33] text-[#4a3219]"
                          : "bg-[#faf7f1] text-[#8c7358] hover:bg-[#efe7d8]/60"
                      }`}
                    >
                      <div className="font-semibold text-[#4a3219]">{t.name}</div>
                      <div className="text-[11px] text-[#8c7358] line-clamp-2 mt-0.5">
                        {t.description}
                      </div>
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => setSelectedTemplate("")}
                    className={`text-left p-3 rounded-lg transition ${
                      selectedTemplate === ""
                        ? "bg-[#efe7d8] ring-2 ring-[#cd8e33] text-[#4a3219]"
                        : "bg-[#faf7f1] text-[#8c7358] hover:bg-[#efe7d8]/60"
                    }`}
                  >
                    <div className="font-semibold text-[#4a3219]">Existing Folder</div>
                    <div className="text-[11px] text-[#8c7358] mt-0.5">
                      Open an existing codebase or research folder
                    </div>
                  </button>
                </div>
              </div>

              <div>
                <div className="block text-[#4a3219] font-medium mb-1">Workspace Folder Path</div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={projPath}
                    onChange={(e) => setProjPath(e.target.value)}
                    placeholder="~/projects/my-research or C:\projects\my-research"
                    className="flex-1 bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                  />
                  <button type="button" onClick={handlePickFolder} className="theta-btn-secondary">
                    <FolderOpen className="w-3.5 h-3.5" />
                    Browse
                  </button>
                </div>
              </div>

              <div>
                <label htmlFor="project-name" className="block text-[#4a3219] font-medium mb-1">
                  Project Name
                </label>
                <input
                  id="project-name"
                  type="text"
                  value={projName}
                  onChange={(e) => setProjName(e.target.value)}
                  placeholder="Research Project"
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                />
              </div>

              <div>
                <label
                  htmlFor="custom-project-instructions-optional"
                  className="block text-[#4a3219] font-medium mb-1"
                >
                  Custom Project Instructions (Optional)
                </label>
                <textarea
                  id="custom-project-instructions-optional"
                  rows={3}
                  value={projInstructions}
                  onChange={(e) => setProjInstructions(e.target.value)}
                  placeholder="Specify project-specific goals, sources, or conventions..."
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                />
              </div>

              {creatingError && (
                <div className="text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2">
                  {creatingError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewProject(false)}
                  className="theta-btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="theta-btn">
                  Create Project
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Persona Modal */}
      {showNewPersona && (
        <div className="fixed inset-0 z-50 bg-[#4a3219]/45 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="theta-card max-w-lg w-full p-6 shadow-2xl max-h-[92vh] overflow-y-auto">
            <div className="flex items-center gap-2 mb-4">
              <UserPlus className="w-5 h-5 text-[#cd8e33]" />
              <h2 className="font-display text-2xl font-semibold text-[#4a3219]">
                Create New Persona
              </h2>
            </div>

            <form onSubmit={handleCreatePersona} className="space-y-3.5 text-xs">
              <div>
                <label htmlFor="persona-name" className="block text-[#4a3219] font-medium mb-1">
                  Persona Name
                </label>
                <input
                  id="persona-name"
                  type="text"
                  value={personaName}
                  onChange={(e) => setPersonaName(e.target.value)}
                  placeholder="e.g. Security Auditor"
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                />
              </div>

              <div>
                <label htmlFor="tagline" className="block text-[#4a3219] font-medium mb-1">
                  Tagline
                </label>
                <input
                  id="tagline"
                  type="text"
                  value={personaTagline}
                  onChange={(e) => setPersonaTagline(e.target.value)}
                  placeholder="Threat modeling, vulnerability review, and hardening"
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                />
              </div>

              <div>
                <label
                  htmlFor="system-instructions"
                  className="block text-[#4a3219] font-medium mb-1"
                >
                  System Instructions
                </label>
                <textarea
                  id="system-instructions"
                  rows={4}
                  value={personaPrompt}
                  onChange={(e) => setPersonaPrompt(e.target.value)}
                  placeholder="Describe how this persona should think, investigate, and respond..."
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                />
              </div>

              <div>
                <label
                  htmlFor="starter-prompts-optional-one-per-line"
                  className="block text-[#4a3219] font-medium mb-1"
                >
                  Starter Prompts (Optional, one per line)
                </label>
                <textarea
                  id="starter-prompts-optional-one-per-line"
                  rows={3}
                  value={personaStarters}
                  onChange={(e) => setPersonaStarters(e.target.value)}
                  placeholder="Audit this project for security risks&#10;Review authentication and input validation"
                  className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
                />
              </div>

              {skills.length > 0 && (
                <div>
                  <div className="block text-[#4a3219] font-medium mb-1">
                    Linked Skills (Optional — leave empty for all enabled)
                  </div>
                  <div className="max-h-28 overflow-y-auto bg-[#f3ece0] rounded-lg p-2 space-y-1">
                    {skills.map((s) => {
                      const checked = personaSkillIds.includes(s.name);
                      return (
                        <label
                          key={s.name}
                          className="flex items-center gap-2 text-[#4a3219] cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) =>
                              setPersonaSkillIds((prev) =>
                                e.target.checked
                                  ? [...prev, s.name]
                                  : prev.filter((id) => id !== s.name),
                              )
                            }
                          />
                          <span className="truncate">{s.name}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              {mcpServers.length > 0 && (
                <div>
                  <div className="block text-[#4a3219] font-medium mb-1">
                    Linked MCP Servers (Optional — leave empty for all enabled)
                  </div>
                  <div className="max-h-28 overflow-y-auto bg-[#f3ece0] rounded-lg p-2 space-y-1">
                    {mcpServers.map((m) => {
                      const checked = personaMcpIds.includes(m.id);
                      return (
                        <label
                          key={m.id}
                          className="flex items-center gap-2 text-[#4a3219] cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) =>
                              setPersonaMcpIds((prev) =>
                                e.target.checked
                                  ? [...prev, m.id]
                                  : prev.filter((id) => id !== m.id),
                              )
                            }
                          />
                          <span className="truncate">{m.name}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

              {personaError && (
                <div className="text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2">{personaError}</div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewPersona(false)}
                  className="theta-btn-secondary"
                >
                  Cancel
                </button>
                <button type="submit" className="theta-btn">
                  Create Persona
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
};
