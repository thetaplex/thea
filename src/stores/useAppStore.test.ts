import { beforeEach, describe, expect, it, vi } from "vitest";

// Every api call resolves to an empty list; `on*` listeners record their handler.
const handlers: Record<string, (ev: unknown) => unknown> = {};
const fns: Record<string, ReturnType<typeof vi.fn>> = {};
vi.mock("../lib/ipc", () => ({
  api: new Proxy(
    {},
    {
      get: (_t, key: string) => {
        fns[key] ??= key.startsWith("on")
          ? vi.fn(async (cb: (ev: unknown) => unknown) => {
              handlers[key] = cb;
              return () => {};
            })
          : vi.fn(async () => (key === "getSettings" ? null : []));
        return fns[key];
      },
    },
  ),
}));

const { useAppStore } = await import("./useAppStore");
const { api } = await import("../lib/ipc");
/** The mock behind `api[key]`, created on first touch. */
const mockOf = (key: string) => {
  void (api as unknown as Record<string, unknown>)[key];
  return fns[key];
};
const file = (p: string) => ({ relative_path: p, is_dir: false });

beforeEach(() => {
  for (const f of Object.values(fns)) f.mockClear();
  useAppStore.setState({
    activeProjectId: null,
    activeChatId: null,
    chats: [],
    projectFiles: [],
    knowledgeFiles: [],
  });
});

describe("chat workspace files", () => {
  it("lists the chat workspace when no project is selected", async () => {
    mockOf("listProjectFiles").mockResolvedValueOnce([file("TASK.md")]);
    useAppStore.setState({ activeChatId: "c1" });
    await useAppStore.getState().refreshProjectFiles();
    expect(mockOf("listProjectFiles")).toHaveBeenCalledWith("chat:c1");
    expect(mockOf("listKnowledgeFiles")).not.toHaveBeenCalled();
    expect(useAppStore.getState().projectFiles).toEqual([file("TASK.md")]);
  });

  it("ignores a file list that arrives after a chat switch", async () => {
    let finishA: (v: unknown) => void = () => {};
    mockOf("listProjectFiles").mockImplementationOnce(() => new Promise((r) => (finishA = r)));
    mockOf("listProjectFiles").mockResolvedValueOnce([file("b.md")]);
    useAppStore.setState({ activeChatId: "a" });
    const slow = useAppStore.getState().refreshProjectFiles();
    useAppStore.setState({ activeChatId: "b" });
    await useAppStore.getState().refreshProjectFiles();
    finishA([file("a.md")]);
    await slow;
    expect(useAppStore.getState().projectFiles).toEqual([file("b.md")]);
  });

  it("refreshes files when selecting a chat without a project", async () => {
    await useAppStore.getState().selectChat("c2");
    expect(mockOf("listProjectFiles")).toHaveBeenCalledWith("chat:c2");
  });

  it("refreshes files when creating a chat without a project", async () => {
    mockOf("createChat").mockResolvedValueOnce({ id: "c3", persona_id: "" });
    await useAppStore.getState().createNewChat();
    expect(mockOf("listProjectFiles")).toHaveBeenCalledWith("chat:c3");
  });

  it("opens a written file only for the chat on screen", async () => {
    await useAppStore.getState().initialize();
    useAppStore.setState({ activeChatId: "c1", chats: [] });
    const done = (chat_id: string) => ({
      chat_id,
      tool_call_id: chat_id,
      tool_name: "write_file",
      status: "done",
      artifact_path: "TASK.md",
    });
    await handlers.onToolEvent(done("other"));
    expect(mockOf("readProjectFile")).not.toHaveBeenCalled();
    await handlers.onToolEvent(done("c1"));
    expect(mockOf("readProjectFile")).toHaveBeenCalledWith("chat:c1", "TASK.md");
  });
});

describe("switching projects", () => {
  it("clears the old project's chat view when the new project has no chats", async () => {
    const old = { id: "x", title: "notes.md", language: "markdown", content: "old" };
    useAppStore.setState({
      activeProjectId: "p1",
      activeChatId: "c1",
      artifacts: [old],
      activeArtifact: old,
      isStreaming: true,
      streamingContent: "half a reply",
      lastError: "boom",
    });
    await useAppStore.getState().selectProject("p2");
    const s = useAppStore.getState();
    expect(s.activeProjectId).toBe("p2");
    expect(s.artifacts).toEqual([]);
    expect(s.activeArtifact).toBeNull();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingContent).toBe("");
    expect(s.lastError).toBeNull();
  });

  it("ignores a chat list that arrives after a second project switch", async () => {
    let finishA: (v: unknown) => void = () => {};
    mockOf("listChats").mockImplementationOnce(() => new Promise((r) => (finishA = r)));
    mockOf("listChats").mockResolvedValueOnce([{ id: "b-chat" }]);
    const slow = useAppStore.getState().selectProject("a");
    await useAppStore.getState().selectProject("b");
    finishA([{ id: "a-chat" }]);
    await slow;
    const s = useAppStore.getState();
    expect(s.activeProjectId).toBe("b");
    expect(s.chats).toEqual([{ id: "b-chat" }]);
    expect(s.activeChatId).toBe("b-chat");
  });
});
