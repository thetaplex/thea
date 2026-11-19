import { Eye, Plus, Sparkles, Trash2 } from "lucide-react";
import type React from "react";
import { useEffect, useState } from "react";
import { api, type Lesson, type SkillInfo } from "../lib/ipc";
import { customSkills } from "../lib/skills";
import { useAppStore } from "../stores/useAppStore";

export const SkillsPane: React.FC = () => {
  const {
    skills: allSkills,
    toggleSkill,
    refreshSkills,
    activeProjectId,
    activePersonaId,
  } = useAppStore();
  const skills = customSkills(allSkills);
  const [selectedSkill, setSelectedSkill] = useState<SkillInfo | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [scope, setScope] = useState<"global" | "project">("global");
  const [body, setBody] = useState(
    "# Skill Instructions\n\n1. Explain when and how Thea should apply this workflow.\n",
  );
  const [error, setError] = useState<string | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [editing, setEditing] = useState<number | null>(null);

  useEffect(() => {
    if (!activePersonaId) return;
    let stale = false;
    api
      .listLessons(activePersonaId)
      .then((l) => !stale && setLessons(l))
      .catch(() => !stale && setLessons([]));
    return () => {
      stale = true;
    };
  }, [activePersonaId]);

  const saveLesson = async (index: number, text: string) => {
    setEditing(null);
    if (!text.trim() || text === lessons[index]?.text) return;
    try {
      await api.updateLesson(activePersonaId, index, text);
      setLessons(await api.listLessons(activePersonaId));
    } catch (err) {
      setError(String(err));
    }
  };

  const removeLesson = async (index: number) => {
    try {
      await api.deleteLesson(activePersonaId, index);
      setLessons(await api.listLessons(activePersonaId));
    } catch (err) {
      setError(String(err));
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !description.trim()) {
      setError("Name and description are required.");
      return;
    }
    try {
      const created = await api.createSkill(activeProjectId, scope, name, description, body);
      await refreshSkills();
      setSelectedSkill(created);
      setShowCreate(false);
      setName("");
      setDescription("");
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f3ece0]">
      <div className="px-4 py-2.5 flex items-center justify-between bg-[#efe7d8]/60">
        <div className="flex items-center gap-2 text-xs font-semibold text-[#4a3219]">
          <Sparkles className="w-3.5 h-3.5 text-[#cd8e33]" />
          <span>Custom Skills ({skills.length})</span>
        </div>
        <button
          type="button"
          onClick={() => {
            setShowCreate(!showCreate);
            setSelectedSkill(null);
          }}
          className="theta-btn !px-2.5 !py-1"
        >
          <Plus className="w-3.5 h-3.5" />
          New Skill
        </button>
      </div>

      {showCreate ? (
        <form onSubmit={handleCreate} className="p-4 space-y-3 overflow-y-auto text-xs">
          <div className="font-display text-lg font-semibold text-[#4a3219]">
            Create Custom SKILL.md
          </div>
          <div>
            <label htmlFor="scope" className="block text-[#8c7358] mb-1">
              Scope
            </label>
            <select
              id="scope"
              value={scope}
              onChange={(e) => setScope(e.target.value as "global" | "project")}
              className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219] shadow-2xs"
            >
              <option value="global">Global (~/.thea/skills)</option>
              <option value="project" disabled={!activeProjectId}>
                Current Project (.thea/skills)
              </option>
            </select>
          </div>
          <div>
            <label htmlFor="skill-name" className="block text-[#8c7358] mb-1">
              Skill Name
            </label>
            <input
              id="skill-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. api-designer"
              className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219] shadow-2xs"
            />
          </div>
          <div>
            <label htmlFor="short-trigger-description" className="block text-[#8c7358] mb-1">
              Short Trigger Description
            </label>
            <input
              id="short-trigger-description"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="When should the model load this skill?"
              className="w-full bg-white rounded-lg px-2.5 py-1.5 text-[#4a3219] shadow-2xs"
            />
          </div>
          <div>
            <label
              htmlFor="markdown-instructions-skill-md-body"
              className="block text-[#8c7358] mb-1"
            >
              Markdown Instructions (SKILL.md body)
            </label>
            <textarea
              id="markdown-instructions-skill-md-body"
              rows={8}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full bg-white rounded-lg p-2.5 text-[#4a3219] font-mono text-[11px] shadow-2xs"
            />
          </div>
          {error && <div className="text-[#7f2217]">{error}</div>}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="theta-btn-secondary"
            >
              Cancel
            </button>
            <button type="submit" className="theta-btn">
              Save Skill
            </button>
          </div>
        </form>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-2.5 text-xs">
          <p className="text-[11px] text-[#8c7358] px-1 pb-1">
            Enabled skills are advertised in the system prompt and loaded on-demand via the{" "}
            <code className="text-[#8b6022] font-semibold">load_capability</code> tool.
          </p>

          {skills.map((skill) => (
            <div key={skill.name} className="theta-card p-3.5 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono font-semibold text-[#4a3219] truncate">
                    {skill.name}
                  </span>
                  <span className="px-2 py-0.5 rounded-md text-[10px] uppercase bg-[#efe7d8] text-[#8c7358] font-medium">
                    {skill.source}
                  </span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedSkill(selectedSkill?.name === skill.name ? null : skill)
                    }
                    className="theta-btn-secondary !p-1"
                    title="Inspect SKILL.md"
                  >
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                  <input
                    type="checkbox"
                    checked={skill.enabled}
                    onChange={(e) => toggleSkill(skill.name, e.target.checked)}
                    className="accent-[#8b6022] w-3.5 h-3.5 cursor-pointer"
                  />
                </div>
              </div>
              <p className="text-[11px] text-[#5c4024] leading-relaxed">{skill.description}</p>

              {selectedSkill?.name === skill.name && (
                <pre className="mt-2 p-2.5 rounded-lg bg-[#2c1e14] text-[#faf7f1] text-[11px] font-mono whitespace-pre-wrap max-h-60 overflow-y-auto">
                  {skill.body}
                </pre>
              )}
            </div>
          ))}

          <div className="px-1 pt-3 text-[11px] font-semibold text-[#4a3219]">
            Lessons ({lessons.length})
          </div>
          {lessons.length === 0 && (
            <p className="text-[11px] text-[#8c7358] px-1">
              None yet. Thea writes one when a citation check, rating or repeated error gives a
              signal.
            </p>
          )}
          {lessons.map((lesson, index) => (
            <div
              key={`${lesson.date}-${lesson.text}`}
              className="theta-card p-3 flex items-start gap-2"
            >
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex items-center gap-2 text-[10px] text-[#8c7358]">
                  <span>{lesson.date}</span>
                  <span className="px-2 py-0.5 rounded-md uppercase bg-[#efe7d8] font-medium">
                    {lesson.signal}
                  </span>
                </div>
                {editing === index ? (
                  <input
                    // biome-ignore lint/a11y/noAutofocus: focus the field the user just clicked to edit
                    autoFocus
                    aria-label="Lesson text"
                    defaultValue={lesson.text}
                    onBlur={(e) => saveLesson(index, e.target.value)}
                    className="w-full bg-white rounded-lg px-2 py-1 text-[#4a3219] shadow-2xs"
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => setEditing(index)}
                    className="text-left text-[11px] text-[#5c4024] leading-relaxed"
                  >
                    {lesson.text}
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => removeLesson(index)}
                className="theta-btn-secondary !p-1 shrink-0"
                title="Delete lesson"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
