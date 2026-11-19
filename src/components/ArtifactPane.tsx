import {
  Check,
  Code,
  Copy,
  Eye,
  FileDown,
  FileText,
  FolderTree,
  Pin,
  RefreshCw,
  Save,
} from "lucide-react";
import type React from "react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../lib/ipc";
import { PREVIEW_CSP, pdfName, printableHtml } from "../lib/print";
import { workspaceId } from "../lib/workspace";
import { useAppStore } from "../stores/useAppStore";

// Model-generated HTML runs with scripts; sandbox blocks DOM/IPC/navigation, PREVIEW_CSP blocks
// fetch/XHR/WS. ponytail: img-src beacons still possible; tighten to img-src data: if that matters.

export const ArtifactPane: React.FC<{ mode: "artifacts" | "files" }> = ({ mode }) => {
  const {
    artifacts,
    activeArtifact,
    setActiveArtifact,
    projectFiles,
    projectFilesError,
    knowledgeFiles,
    activeProjectId,
    activeChatId,
    openFileInArtifact,
    refreshProjectFiles,
  } = useAppStore();

  const [viewMode, setViewMode] = useState<"preview" | "code">("preview");
  const [editedContent, setEditedContent] = useState("");
  const [copied, setCopied] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  // Bumped by Refresh: a new key reloads the preview iframe, so its scripts run again.
  const [frameKey, setFrameKey] = useState(0);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const refreshFiles = async () => {
    setRefreshing(true);
    try {
      await refreshProjectFiles();
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (activeArtifact) {
      setEditedContent(activeArtifact.content);
      const isRenderable =
        activeArtifact.language === "html" ||
        activeArtifact.language === "svg" ||
        activeArtifact.language === "markdown";
      setViewMode(isRenderable ? "preview" : "code");
    }
  }, [activeArtifact]);

  if (mode === "files") {
    const pinnedSet = new Set(knowledgeFiles.map((k) => k.relative_path));

    const togglePin = async (relPath: string) => {
      if (!activeProjectId) return;
      const existing = knowledgeFiles.find((k) => k.relative_path === relPath);
      if (existing) {
        await api.removeKnowledgeFile(existing.id);
      } else {
        await api.addKnowledgeFile(activeProjectId, relPath);
      }
      await refreshProjectFiles();
    };

    return (
      <div className="flex-1 flex flex-col overflow-hidden bg-[#f3ece0]">
        <div className="px-4 py-2.5 flex items-center justify-between text-xs text-[#8c7358] bg-[#efe7d8]/60">
          <span className="flex items-center gap-1.5 font-semibold text-[#4a3219]">
            <FolderTree className="w-3.5 h-3.5 text-[#cd8e33]" />
            Workspace Files
          </span>
          <button
            type="button"
            onClick={refreshFiles}
            disabled={refreshing}
            className="theta-btn-secondary !px-2.5 !py-1"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-1 text-xs">
          {!workspaceId(activeProjectId, activeChatId) ? (
            <div className="text-[#8c7358] text-center py-8">
              Select a project or a chat in the left sidebar to browse its files.
            </div>
          ) : projectFilesError ? (
            <div className="text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2 break-words">
              Could not list files: {projectFilesError}
            </div>
          ) : projectFiles.length === 0 ? (
            <div className="text-[#8c7358] text-center py-8">Workspace folder is empty.</div>
          ) : (
            projectFiles.map((f) => {
              const isPinned = pinnedSet.has(f.relative_path);
              return (
                <div
                  key={f.relative_path}
                  className="flex items-center justify-between px-2.5 py-1.5 rounded-lg hover:bg-[#e8decb]/70 group"
                >
                  <button
                    type="button"
                    onClick={() => !f.is_dir && openFileInArtifact(f.relative_path)}
                    disabled={f.is_dir}
                    className={`flex items-center gap-2 truncate text-left ${
                      f.is_dir
                        ? "text-[#8c7358] font-medium cursor-default"
                        : "text-[#4a3219] hover:text-[#8b6022]"
                    }`}
                  >
                    <FileText className="w-3.5 h-3.5 shrink-0 text-[#8b6022]" />
                    <span className="truncate">
                      {f.relative_path}
                      {f.is_dir ? "/" : ""}
                    </span>
                  </button>
                  {!f.is_dir && activeProjectId && (
                    <button
                      type="button"
                      onClick={() => togglePin(f.relative_path)}
                      title={
                        isPinned
                          ? "Pinned to Project Knowledge (click to unpin)"
                          : "Pin file to Project Knowledge context"
                      }
                      className={`theta-btn-secondary !p-1 ${
                        isPinned ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                      }`}
                    >
                      <Pin className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    );
  }

  // Artifacts mode
  const handleCopy = async () => {
    if (!activeArtifact) return;
    await navigator.clipboard.writeText(editedContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleRefresh = async () => {
    if (activeArtifact?.sourcePath) await openFileInArtifact(activeArtifact.sourcePath);
    setFrameKey((k) => k + 1);
  };

  const handlePdf = async () => {
    if (!activeArtifact) return;
    setPdfError(null);
    try {
      await api.printArtifact(
        pdfName(activeArtifact),
        printableHtml(activeArtifact, editedContent),
      );
    } catch (err) {
      setPdfError(String(err));
    }
  };

  const handleSaveToProject = async () => {
    if (!activeArtifact || !activeProjectId) return;
    const relPath =
      activeArtifact.sourcePath ||
      (activeArtifact.language === "html" ? "index.html" : "artifact.txt");
    await api.writeProjectFile(activeProjectId, relPath, editedContent);
    await refreshProjectFiles();
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 1500);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#f3ece0]">
      {/* Artifact selector bar */}
      <div className="px-3 py-2 flex items-center justify-between gap-2 bg-[#efe7d8]/60">
        <select
          value={activeArtifact?.id ?? ""}
          onChange={(e) => {
            const found = artifacts.find((a) => a.id === e.target.value);
            if (found) setActiveArtifact(found);
          }}
          className="bg-white rounded-lg px-2.5 py-1.5 text-xs text-[#4a3219] truncate flex-1 shadow-2xs"
        >
          {activeArtifact && !artifacts.some((a) => a.id === activeArtifact.id) && (
            <option value={activeArtifact.id}>{activeArtifact.title}</option>
          )}
          {artifacts.length === 0 && !activeArtifact && <option value="">No artifacts yet</option>}
          {artifacts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.title} ({a.language})
            </option>
          ))}
        </select>

        {activeArtifact && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setViewMode("preview")}
              className={
                viewMode === "preview"
                  ? "theta-btn !px-2.5 !py-1"
                  : "theta-btn-secondary !px-2.5 !py-1"
              }
            >
              <Eye className="w-3.5 h-3.5" />
              Preview
            </button>
            <button
              type="button"
              onClick={() => setViewMode("code")}
              className={
                viewMode === "code"
                  ? "theta-btn !px-2.5 !py-1"
                  : "theta-btn-secondary !px-2.5 !py-1"
              }
            >
              <Code className="w-3.5 h-3.5" />
              Code
            </button>
            <button
              type="button"
              onClick={handleRefresh}
              title={
                activeArtifact.sourcePath
                  ? "Reload the file from the project folder"
                  : "Reload the preview"
              }
              className="theta-btn-secondary !p-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handlePdf}
              title="Save as PDF (opens the print dialog)"
              className="theta-btn-secondary !p-1.5"
            >
              <FileDown className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={handleCopy}
              title="Copy content"
              className="theta-btn-secondary !p-1.5"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-700" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
            {activeProjectId && (
              <button
                type="button"
                onClick={handleSaveToProject}
                title="Save changes back to project workspace"
                className="theta-btn-secondary !p-1.5"
              >
                {savedNotice ? (
                  <Check className="w-3.5 h-3.5 text-emerald-700" />
                ) : (
                  <Save className="w-3.5 h-3.5" />
                )}
              </button>
            )}
          </div>
        )}
      </div>

      {pdfError && (
        <div className="mx-3 mt-2 text-xs text-[#7f2217] bg-rose-50 rounded-lg px-3 py-2 break-words">
          Could not open the PDF view: {pdfError}
        </div>
      )}

      {/* Body */}
      <div className="flex-1 overflow-auto p-3 bg-[#f3ece0]">
        {!activeArtifact ? (
          <div className="h-full flex items-center justify-center p-6 text-center text-xs text-[#8c7358]">
            Code blocks, HTML prototypes, and files opened from your project will appear here for
            live preview and editing.
          </div>
        ) : viewMode === "preview" &&
          (activeArtifact.language === "html" || activeArtifact.language === "svg") ? (
          <iframe
            key={frameKey}
            title={activeArtifact.title}
            srcDoc={PREVIEW_CSP + editedContent}
            sandbox="allow-scripts"
            className="w-full h-full border-0 rounded-xl bg-white shadow-xs"
          />
        ) : viewMode === "preview" && activeArtifact.language === "markdown" ? (
          <div className="p-5 rounded-xl bg-white shadow-xs prose prose-sm max-w-none theta-prose">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{editedContent}</ReactMarkdown>
          </div>
        ) : (
          <textarea
            value={editedContent}
            onChange={(e) => setEditedContent(e.target.value)}
            spellCheck={false}
            className="w-full h-full rounded-xl bg-[#2c1e14] text-[#faf7f1] font-mono text-xs p-4 resize-none leading-relaxed"
          />
        )}
      </div>
    </div>
  );
};
