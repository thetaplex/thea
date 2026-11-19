# Chat Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A chat without a project runs in its own scratch folder `~/.thea/chats/<chat-id>/` with the persona's full tool set, and the Personal Assistant loads only its own skills.

**Architecture:** `Database::get_project` resolves an id of the form `chat:<chat-id>` to an in-memory `Project` rooted at the chat folder. Because every consumer (agent turn, tool execution, approvals, `TASK.md` nudges, the Files commands in `lib.rs`) already goes through `Option<&Project>` or `get_project`, they work unchanged. The frontend uses the same id when no project is selected.

**Tech Stack:** Rust (Tauri 2, rusqlite), React + Zustand, Vitest.

**Spec:** `docs/dev/superpowers/specs/2026-11-15-chat-workspace-design.md`

## Global Constraints

- Folder: `thea_home_dir().join("chats").join(<chat-id>)` (honours `THEA_HOME`).
- Stand-in id: `chat:<chat-id>`; constant `CHAT_WORKSPACE_PREFIX: &str = "chat:"` in `src-tauri/src/db.rs`.
- No database schema change. `chats.project_id` stays `NULL`.
- Knowledge-file pinning stays project-only.
- Docs under `docs/` (outside `docs/dev/superpowers/`) must pass `repo_docs_pass_ste_style` (`ASD-STE100`).
- `just check` passes after every task.

## Review Focus

1. `delete_chat` with a crafted id such as `../..` must never remove anything outside `~/.thea/chats/`: delete the folder only for a chat that exists in the database. Test in Task 1.
2. `get_project("chat:<id>")` for an unknown chat, or for a chat that has a real project, returns `None`, so the Files commands cannot open an arbitrary path. Test in Task 1.
3. Opening the Files pane for a new chat before its first turn shows "Workspace folder is empty", not an error: the stand-in creates the folder. Test in Task 1.
4. A chat whose project was deleted is removed by `ON DELETE CASCADE`, so no stale chat falls through to a scratch folder. No new code; covered by the existing cascade.
5. Switching from a project to "no project" and selecting a chat refreshes the Files pane to that chat's folder. Test in Task 2 (pure helper).

---

### Task 1: Backend chat workspace

**Files:**
- Modify: `src-tauri/src/db.rs` (`get_project` ~1192, `delete_chat` ~1426, tests module)
- Modify: `src-tauri/src/agent/mod.rs` (`base_tool_definitions` ~169, turn setup ~437-462, test `no_project_offers_research_tools` ~1657)
- Modify: `docs/reference/storage-and-settings.md`, `CHANGELOG.md`

**Interfaces:**
- Produces: `pub const CHAT_WORKSPACE_PREFIX: &str = "chat:";`
- Produces: `pub fn chat_workspace_dir(chat_id: &str) -> PathBuf` in `db.rs`
- Produces: `Database::workspace_for_chat(&self, chat: &Chat) -> Result<Option<Project>>`: the real project when `chat.project_id` is `Some`, otherwise `get_project(&format!("{CHAT_WORKSPACE_PREFIX}{}", chat.id))`.
- Produces: `get_project` returns, for `chat:<id>` where the chat exists and has `project_id == None`, `Project { id: "chat:<id>", name: "Chat workspace", root_path: chat_workspace_dir(id), instructions: "", persona_id: chat.persona_id, created_at/updated_at: chat's }` and creates the folder (`create_dir_all`). Any other `chat:` id gives `None`. Check the prefix before taking the connection lock (`get_chat` locks too).
- Produces: `base_tool_definitions() -> Vec<ToolDefinition>` with no parameter (the `has_project` filter is removed).

- [ ] **Step 1: Write the failing tests in `db.rs` tests**

```rust
#[test]
fn chat_without_project_gets_scratch_workspace() {
    let _g = test_env_lock();
    let dir = tempfile::tempdir().unwrap();
    std::env::set_var("THEA_HOME", dir.path());
    let db = Database::open(&dir.path().join("t.sqlite3")).unwrap();
    let chat = db.create_chat(None, "personal-assistant", "t", "ollama", "m").unwrap();
    let ws = db.workspace_for_chat(&chat).unwrap().unwrap();
    assert_eq!(ws.id, format!("chat:{}", chat.id));
    assert_eq!(PathBuf::from(&ws.root_path), dir.path().join("chats").join(&chat.id));
    assert!(PathBuf::from(&ws.root_path).is_dir());
    assert_eq!(ws.persona_id, "personal-assistant");
}

#[test]
fn chat_workspace_id_only_resolves_for_projectless_chats() {
    // setup as above
    assert!(db.get_project("chat:no-such-chat").unwrap().is_none());
    assert!(db.get_project("chat:../..").unwrap().is_none());
    let p = db
        .create_project("p", dir.path().to_str().unwrap(), "", "personal-assistant")
        .unwrap();
    let c = db.create_chat(Some(&p.id), "personal-assistant", "t", "ollama", "m").unwrap();
    assert!(db.get_project(&format!("chat:{}", c.id)).unwrap().is_none());
}

#[test]
fn delete_chat_removes_its_workspace_only() {
    // setup as above
    let chat = db.create_chat(None, "personal-assistant", "t", "ollama", "m").unwrap();
    let root = PathBuf::from(db.workspace_for_chat(&chat).unwrap().unwrap().root_path);
    std::fs::write(root.join("TASK.md"), "x").unwrap();
    let sentinel = dir.path().join("keep.txt");
    std::fs::write(&sentinel, "x").unwrap();
    db.delete_chat("..").unwrap();
    assert!(sentinel.exists());
    db.delete_chat(&chat.id).unwrap();
    assert!(!root.exists());
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cargo test --manifest-path src-tauri/Cargo.toml chat_ -- --nocapture`
Expected: FAIL to compile (`workspace_for_chat` not defined).

- [ ] **Step 3: Implement `CHAT_WORKSPACE_PREFIX`, `chat_workspace_dir`, the `chat:` branch of `get_project`, `workspace_for_chat`, and folder removal in `delete_chat`**

`delete_chat`: look up the chat first; delete the row; then, only if the chat existed, `remove_dir_all(chat_workspace_dir(id))`, ignoring `NotFound`.

- [ ] **Step 4: Wire the agent turn**

In `run_agent_turn_with_reflection` replace the `match &chat.project_id` block with `let project = db.workspace_for_chat(&chat)?;`. Change `base_tool_definitions(project.is_some())` to `base_tool_definitions()` and drop the parameter and filter. Delete the test `no_project_offers_research_tools`.

- [ ] **Step 5: Run the tests**

Run: `just check`
Expected: exit 0, the three new tests pass.

- [ ] **Step 6: Docs**

In `docs/reference/storage-and-settings.md` add a Global Files row: `` `~/.thea/chats/<chat-id>/` `` | Folder | Workspace for a chat without a project. It has the same layout as a project workspace. Thea deletes it when you delete the chat. Also fix the stale row `` `<project>/docket/reviews/*.md` `` to two rows: `` `<project>/docket/drafts/*.md` `` (emails, memos, and agendas that cite `[D#]` keys) and `` `<project>/docket/plans/*.md` `` (action plans that cite `[D#]` keys). Add to `CHANGELOG.md` under Added: "- A chat without a project has its own workspace folder in `~/.thea/chats/` and uses all the tools of its persona." Run `just check` again.

- [ ] **Step 7: Commit**

```bash
git add src-tauri/src/db.rs src-tauri/src/agent/mod.rs docs/reference/storage-and-settings.md CHANGELOG.md
git commit -m "feat: give chats without a project a scratch workspace in ~/.thea/chats"
```

### Task 2: Files pane for a chat workspace

**Files:**
- Create: `src/lib/workspace.ts`, `src/lib/workspace.test.ts`
- Modify: `src/stores/useAppStore.ts` (`refreshProjectFiles` ~333, `openFileInArtifact` ~473, tool-event handler ~214, `selectChat` ~347)
- Modify: `src/components/ArtifactPane.tsx` (empty state ~84, pin toggle ~56)

**Interfaces:**
- Consumes: backend `chat:<chat-id>` ids resolve in `listProjectFiles` and `readProjectFile` (Task 1).
- Produces: `export function workspaceId(projectId: string | null, chatId: string | null): string | null` returning `projectId`, else `` `chat:${chatId}` ``, else `null`.

- [ ] **Step 1: Write the failing test `src/lib/workspace.test.ts`**

```ts
import { describe, expect, it } from "vitest";
import { workspaceId } from "./workspace";

describe("workspaceId", () => {
  it("prefers the project", () => expect(workspaceId("p1", "c1")).toBe("p1"));
  it("falls back to the chat workspace", () => expect(workspaceId(null, "c1")).toBe("chat:c1"));
  it("is null with neither", () => expect(workspaceId(null, null)).toBeNull());
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pnpm test`
Expected: FAIL, cannot resolve `./workspace`.

- [ ] **Step 3: Implement `workspaceId` and use it**

- `refreshProjectFiles` and `openFileInArtifact`: use `workspaceId(activeProjectId, activeChatId)` instead of `activeProjectId`. Call `listKnowledgeFiles` only when `activeProjectId` is set; otherwise set `knowledgeFiles: []`.
- Tool-event handler: refresh when `workspaceId(...)` is non-null, not only when `activeProjectId` is set.
- `selectChat`: when `activeProjectId` is null, call `refreshProjectFiles()` after the chat becomes active (and clear `projectFiles` when `chatId` is null).
- `ArtifactPane`: the "Select or create a project" empty state shows only when `workspaceId(...)` is null; hide the pin button when `activeProjectId` is null.

- [ ] **Step 4: Run the checks**

Run: `just check`
Expected: exit 0, three `workspaceId` tests pass.

- [ ] **Step 5: Manual check**

Run `just run`, select no project, start a chat with the Personal Assistant, ask it to add a Docket task. Expected: an approval card appears, and after approval `docket/DOCKET.md` shows in the Files tab.

- [ ] **Step 6: Commit**

```bash
git add src/lib/workspace.ts src/lib/workspace.test.ts src/stores/useAppStore.ts src/components/ArtifactPane.tsx
git commit -m "feat: show a chat's workspace files when no project is selected"
```

### Task 3: Personal Assistant skills and reading rule

**Files:**
- Modify: `src-tauri/src/db.rs` (`personal-assistant` in `default_personas` ~549, tests module)
- Modify: `docs/reference/providers-and-personas.md` if it lists persona skills

**Interfaces:**
- Produces: `personal-assistant.skill_ids == ["task-checklist", "think-in-steps", "manage-docket", "draft-communication", "weekly-review", "write-ste"]`.

- [ ] **Step 1: Write the failing test in `db.rs` tests**

```rust
#[test]
fn personal_assistant_loads_only_its_skills() {
    let pa = default_personas().into_iter().find(|p| p.id == "personal-assistant").unwrap();
    assert!(!pa.skill_ids.iter().any(|s| s == "research-method"));
    for s in ["task-checklist", "manage-docket", "draft-communication", "weekly-review"] {
        assert!(pa.skill_ids.iter().any(|x| x == s), "{s} missing");
    }
    assert!(pa.system_prompt.contains("fetch_url"));
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cargo test --manifest-path src-tauri/Cargo.toml personal_assistant_loads_only_its_skills`
Expected: FAIL on the `research-method` or `task-checklist` assertion.

- [ ] **Step 3: Set `skill_ids` and add the rule**

Set the six skill ids above. Add to the Rules list of the system prompt, exactly: `- Search once for each option. Before you state a fact such as a visa rule, a price, or a date, read an official page with fetch_url.`

- [ ] **Step 4: Run the checks**

Run: `just check`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add src-tauri/src/db.rs docs/reference/providers-and-personas.md
git commit -m "fix: limit Personal Assistant skills and make it read pages before it states facts"
```
