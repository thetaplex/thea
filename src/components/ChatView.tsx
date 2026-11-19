import {
  Check,
  Code2,
  Loader2,
  Send,
  ShieldAlert,
  Square,
  Terminal,
  ThumbsDown,
  ThumbsUp,
  Wrench,
  X,
} from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { extractArtifactsFromMarkdown } from "../lib/artifacts";
import { chatGreeting } from "../lib/greeting";
import { api } from "../lib/ipc";
import { useAppStore } from "../stores/useAppStore";

export const ChatView: React.FC = () => {
  const {
    activeChatId,
    sessionModel,
    messages,
    streamingContent,
    isStreaming,
    toolEvents,
    lastError,
    incomplete,
    round,
    personas,
    activePersonaId,
    sendMessage,
    stopGeneration,
    pendingApprovals,
    decideApproval,
    setActiveArtifact,
    activeProjectId,
    projects,
  } = useAppStore();

  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const [thanks, setThanks] = useState(false);
  useEffect(() => {
    if (!thanks) return;
    const t = setTimeout(() => setThanks(false), 3000);
    return () => clearTimeout(t);
  }, [thanks]);
  const lastAssistantId = [...messages].reverse().find((m) => m.role === "assistant")?.id;
  // One rating per message: a repeat click would start a repeat reflection.
  const [rated, setRated] = useState<Record<string, boolean>>({});
  const rate = (messageId: string, up: boolean) => {
    if (!activeChatId || rated[messageId]) return;
    setRated((r) => ({ ...r, [messageId]: true }));
    api
      .rateMessage(activeChatId, messageId, up)
      .then(() => setThanks(true))
      .catch(() => setRated((r) => ({ ...r, [messageId]: false })));
  };

  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  // Only a project has a persona; a chat without one gets the time-of-day greeting.
  const activePersona = personas.find((p) => p.id === activePersonaId) ?? null;
  const currentModel = sessionModel || "no model selected";
  const runningTools = Object.values(toolEvents).filter(
    (ev) => ev.chat_id === activeChatId && ev.status === "running",
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-scroll whenever chat height can change
  useEffect(() => {
    // Smooth scrolling fights a fast-growing container in WebKit and leaves blank space; jump while streaming.
    bottomRef.current?.scrollIntoView({ behavior: isStreaming ? "auto" : "smooth" });
  }, [
    messages.length,
    streamingContent,
    isStreaming,
    pendingApprovals.length,
    runningTools.length,
  ]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;
    const text = input;
    setInput("");
    await sendMessage(text);
  };

  const currentGreeting = activePersona
    ? {
        heading: activePersona.greeting || "What should we work on today?",
        subtitle:
          activePersona.subtitle ||
          activePersona.tagline ||
          "Share what's on your mind and we'll tackle it together.",
      }
    : {
        heading: chatGreeting(),
        subtitle: "Ask anything. I can search the web, read files and save a summary of our chat.",
      };

  return (
    <section className="flex-1 flex flex-col h-full bg-[#faf7f1] min-w-0">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {messages.length === 0 && !streamingContent && !isStreaming && (
          <div className="max-w-2xl mx-auto mt-8 theta-hero-bg rounded-2xl p-8 text-center space-y-4 shadow-xs">
            {activeProject && (
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#efe7d8] text-[#8b6022] text-xs font-medium">
                <span>{activeProject.name}</span>
              </div>
            )}
            <h1 className="font-display text-3xl font-semibold text-[#4a3219]">
              {currentGreeting.heading}
            </h1>
            <p className="text-xs text-[#5c4024] max-w-lg mx-auto leading-relaxed">
              {currentGreeting.subtitle}
            </p>
          </div>
        )}

        {messages.map((msg, idx) => {
          if (msg.role === "tool" && msg.tool_name?.endsWith("__sequentialthinking")) {
            let thought: string = msg.content;
            const prev = messages
              .slice(0, idx)
              .reverse()
              .find((m) => m.role === "assistant");
            if (prev?.tool_calls_json) {
              try {
                const calls = JSON.parse(prev.tool_calls_json) as Array<{
                  id: string;
                  arguments: { thought?: unknown };
                }>;
                const t = calls.find((c) => c.id === msg.tool_call_id)?.arguments?.thought;
                if (typeof t === "string") thought = t;
              } catch {
                /* fall back to raw output */
              }
            }
            return (
              <details
                key={msg.id}
                className="max-w-3xl mx-auto bg-[#2c1e14] text-[#faf7f1] rounded-xl p-3.5 text-xs shadow-xs"
              >
                <summary className="cursor-pointer text-[#cd8e33] font-semibold">Thought</summary>
                <p className="mt-1.5 whitespace-pre-wrap text-[#efe7d8]">{thought}</p>
              </details>
            );
          }
          if (msg.role === "tool") {
            return (
              <div
                key={msg.id}
                className="max-w-3xl mx-auto bg-[#2c1e14] text-[#faf7f1] rounded-xl p-3.5 text-xs font-mono shadow-xs"
              >
                <div className="flex items-center gap-2 text-[#cd8e33] mb-1.5 font-sans">
                  <Terminal className="w-3.5 h-3.5" />
                  <span className="font-semibold">Tool Output: {msg.tool_name || "tool"}</span>
                </div>
                <pre className="text-[11px] text-[#efe7d8] overflow-x-auto whitespace-pre-wrap max-h-48">
                  {msg.content}
                </pre>
              </div>
            );
          }

          const isUser = msg.role === "user";
          const msgArtifacts = !isUser ? extractArtifactsFromMarkdown(msg.content, msg.id) : [];
          const parsedToolCalls = msg.tool_calls_json
            ? (() => {
                try {
                  return JSON.parse(msg.tool_calls_json) as Array<{
                    id: string;
                    name: string;
                    arguments: Record<string, unknown>;
                  }>;
                } catch {
                  return [];
                }
              })()
            : [];

          return (
            <div
              key={msg.id}
              id={`msg-${msg.id}`}
              className={`max-w-3xl mx-auto flex flex-col ${isUser ? "items-end" : "items-start"}`}
            >
              <div
                className={`px-4 py-3.5 text-sm leading-relaxed max-w-full ${
                  isUser
                    ? "bg-[#8b6022] text-white rounded-2xl shadow-xs"
                    : "theta-card text-[#5c4024] w-full"
                }`}
              >
                <div
                  className={
                    isUser
                      ? "prose prose-invert prose-sm max-w-none"
                      : "prose prose-sm max-w-none theta-prose"
                  }
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>

                {parsedToolCalls.length > 0 && (
                  <div className="mt-3 pt-2.5 space-y-1.5">
                    {parsedToolCalls.map((tc) => (
                      <div
                        key={tc.id}
                        className="flex items-center gap-2 text-xs text-[#5e4016] bg-[#f3ece0] rounded-lg px-2.5 py-1.5"
                      >
                        <Wrench className="w-3.5 h-3.5 shrink-0 text-[#cd8e33]" />
                        <span className="font-mono font-semibold">{tc.name}</span>
                        <span className="text-[#8c7358] truncate font-mono text-[11px]">
                          {JSON.stringify(tc.arguments)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {msgArtifacts.length > 0 && (
                  <div className="mt-3 pt-2.5 flex flex-wrap gap-2">
                    {msgArtifacts.map((art) => (
                      <button
                        type="button"
                        key={art.id}
                        onClick={() => setActiveArtifact(art)}
                        className="theta-btn-secondary"
                      >
                        <Code2 className="w-3.5 h-3.5" />
                        <span>Open in Artifacts: {art.title}</span>
                      </button>
                    ))}
                  </div>
                )}

                {!isStreaming && msg.id === lastAssistantId && (
                  <div className="mt-3 flex items-center gap-2 text-[#8c7358]">
                    <button
                      type="button"
                      onClick={() => rate(msg.id, true)}
                      disabled={!!rated[msg.id]}
                      title="Good answer"
                      className="theta-btn-secondary !p-1"
                    >
                      <ThumbsUp className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => rate(msg.id, false)}
                      disabled={!!rated[msg.id]}
                      title="Bad answer"
                      className="theta-btn-secondary !p-1"
                    >
                      <ThumbsDown className="w-3.5 h-3.5" />
                    </button>
                    {thanks && (
                      <span className="text-[11px]">
                        Thanks. Lesson saved when the model finds one.
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Live streaming assistant bubble or initial thinking indicator */}
        {isStreaming && (
          <div className="max-w-3xl mx-auto">
            <div className="theta-card px-4 py-3.5 text-sm leading-relaxed text-[#5c4024] space-y-2">
              <div className="flex items-center gap-2 text-xs text-[#8b6022]">
                <Loader2 className="w-4 h-4 animate-spin text-[#cd8e33] shrink-0" />
                <span className="font-semibold">
                  {runningTools.length > 0
                    ? `${round ? `Round ${round.round}/${round.max_rounds}: ` : ""}Running ${runningTools.map((t) => t.tool_name).join(", ")}...`
                    : streamingContent
                      ? `Generating response (${currentModel})...`
                      : `Waiting for ${currentModel}...`}
                </span>
                <span className="flex items-center gap-1 ml-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#cd8e33] animate-bounce [animation-delay:-0.3s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-[#cd8e33] animate-bounce [animation-delay:-0.15s]" />
                  <span className="w-1.5 h-1.5 rounded-full bg-[#cd8e33] animate-bounce" />
                </span>
              </div>

              {streamingContent && (
                <div className="prose prose-sm max-w-none theta-prose pt-2">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Inline Approval Gate Cards */}
        {pendingApprovals.map((req) => (
          <div key={req.request_id} className="max-w-3xl mx-auto theta-card p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-[#4a3219] font-semibold text-xs">
                <ShieldAlert className="w-4 h-4 text-[#cd8e33]" />
                <span>Human-in-the-Loop Approval — {req.summary}</span>
              </div>
              <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-lg bg-[#efe7d8] text-[#8b6022]">
                {req.tool_name}
              </span>
            </div>

            <pre className="text-xs font-mono bg-[#f3ece0] rounded-lg p-2.5 text-[#4a3219] overflow-x-auto">
              {req.details}
            </pre>

            {req.diff && (
              <pre className="text-[11px] font-mono bg-[#2c1e14] text-[#faf7f1] rounded-lg p-3 overflow-x-auto max-h-56">
                {req.diff}
              </pre>
            )}

            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => decideApproval(req.request_id, "approve")}
                className="theta-btn"
              >
                <Check className="w-3.5 h-3.5" />
                Approve Once
              </button>
              {req.tool_name !== "run_command" && (
                <button
                  type="button"
                  onClick={() => decideApproval(req.request_id, "always_allow_project")}
                  className="theta-btn-secondary"
                >
                  <Check className="w-3.5 h-3.5" />
                  Always Allow for Project
                </button>
              )}
              <button
                type="button"
                onClick={() => decideApproval(req.request_id, "reject")}
                className="theta-btn-danger ml-auto"
              >
                <X className="w-3.5 h-3.5" />
                Reject
              </button>
            </div>
          </div>
        ))}

        {incomplete && !isStreaming && (
          <div className="max-w-3xl mx-auto bg-amber-50 text-[#5e4016] rounded-xl p-3.5 text-xs shadow-2xs space-y-2">
            <div className="font-semibold">Task not complete. {incomplete.reason}</div>
            {incomplete.open_items.length > 0 && (
              <ul className="list-disc pl-4 space-y-0.5">
                {incomplete.open_items.map((it) => (
                  <li key={it}>{it.replace(/^- \[ \]\s*/, "")}</li>
                ))}
              </ul>
            )}
            <button
              type="button"
              onClick={() => sendMessage("Continue with the open items in TASK.md.")}
              className="theta-btn !px-3 !py-1.5"
            >
              Continue
            </button>
          </div>
        )}

        {lastError && (
          <div className="max-w-3xl mx-auto bg-rose-50 text-[#5e4016] rounded-xl p-3.5 text-xs shadow-2xs">
            <strong>Error:</strong> {lastError}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <form onSubmit={handleSubmit} className="p-4 bg-[#f3ece0]/65">
        <div className="max-w-3xl mx-auto flex items-end gap-2 bg-white border border-transparent focus-within:border-[#cd8e33] focus-within:ring-2 focus-within:ring-[#cd8e33]/25 rounded-xl p-2.5 shadow-sm transition">
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(e);
              }
            }}
            placeholder={
              activeProject
                ? `Ask Thea in ${activeProject.name}...`
                : "Ask Thea (Shift+Enter for newline)..."
            }
            className="flex-1 bg-transparent text-sm text-[#4a3219] placeholder-[#8c7358] !border-none !shadow-none resize-none px-2 py-1"
          />
          {isStreaming ? (
            <button type="button" onClick={stopGeneration} className="theta-btn-danger shrink-0">
              <Square className="w-3.5 h-3.5 fill-current" />
              Stop
            </button>
          ) : (
            <button type="submit" disabled={!input.trim()} className="theta-btn shrink-0">
              <Send className="w-3.5 h-3.5" />
              Send
            </button>
          )}
        </div>
      </form>
    </section>
  );
};
