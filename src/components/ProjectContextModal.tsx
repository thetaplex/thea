import { Trash2, X } from "lucide-react";
import type React from "react";
import { useState } from "react";
import { api } from "../lib/ipc";
import { useAppStore } from "../stores/useAppStore";

export const ProjectContextModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const {
    projects,
    personas,
    activeProjectId,
    knowledgeFiles,
    refreshProjectFiles,
    initialize,
    selectProject,
  } = useAppStore();

  const project = projects.find((p) => p.id === activeProjectId);
  const [name, setName] = useState(project?.name ?? "");
  const [personaId, setPersonaId] = useState(project?.persona_id ?? personas[0]?.id ?? "");
  const [instructions, setInstructions] = useState(project?.instructions ?? "");

  if (!project) return null;

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.updateProject(project.id, name, instructions, personaId);
    await initialize();
    await selectProject(project.id);
    onClose();
  };

  const handleDeleteProject = async () => {
    await api.deleteProject(project.id);
    await initialize();
    await selectProject(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-[#4a3219]/45 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="theta-card max-w-lg w-full p-6 shadow-2xl space-y-4 text-xs">
        <div className="flex items-center justify-between pb-2">
          <h2 className="font-display text-xl font-semibold text-[#4a3219]">
            Project Context &amp; Persona
          </h2>
          <button type="button" onClick={onClose} className="theta-btn-secondary !p-1.5">
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSave} className="space-y-3.5">
          <div>
            <label htmlFor="project-name" className="block text-[#8c7358] mb-1">
              Project Name
            </label>
            <input
              id="project-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-[#f3ece0] rounded-lg px-3 py-2 text-[#4a3219]"
            />
          </div>

          <div>
            <label htmlFor="default-project-persona" className="block text-[#8c7358] mb-1">
              Default Project Persona
            </label>
            <select
              id="default-project-persona"
              value={personaId}
              onChange={(e) => setPersonaId(e.target.value)}
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
            <div className="block text-[#8c7358] mb-1">Workspace Root</div>
            <div className="bg-[#f3ece0] rounded-lg px-3 py-2 text-[#8c7358] font-mono">
              {project.root_path}
            </div>
          </div>

          <div>
            <label htmlFor="project-system-instructions" className="block text-[#8c7358] mb-1">
              Project System Instructions
            </label>
            <textarea
              id="project-system-instructions"
              rows={5}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              className="w-full bg-[#f3ece0] rounded-lg p-3 text-[#4a3219]"
            />
          </div>

          <div>
            <div className="block text-[#8c7358] mb-1">
              Pinned Knowledge Files ({knowledgeFiles.length})
            </div>
            {knowledgeFiles.length === 0 ? (
              <div className="text-[#8c7358] italic">
                Pin files from the Files tab in the right pane to inject their contents
                automatically into every chat in this project.
              </div>
            ) : (
              <div className="space-y-1">
                {knowledgeFiles.map((kf) => (
                  <div
                    key={kf.id}
                    className="flex items-center justify-between bg-[#f3ece0] rounded-lg px-2.5 py-1.5"
                  >
                    <span className="font-mono text-[#4a3219]">{kf.relative_path}</span>
                    <button
                      type="button"
                      onClick={async () => {
                        await api.removeKnowledgeFile(kf.id);
                        await refreshProjectFiles();
                      }}
                      className="theta-btn-secondary !p-1"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center justify-between pt-2">
            <button type="button" onClick={handleDeleteProject} className="theta-btn-danger">
              <Trash2 className="w-3.5 h-3.5" />
              Remove Project
            </button>
            <div className="flex gap-2">
              <button type="button" onClick={onClose} className="theta-btn-secondary">
                Cancel
              </button>
              <button type="submit" className="theta-btn">
                Save
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
