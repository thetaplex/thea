# Chat workspace: a scratch folder for chats without a project

Date: 2026-11-15. Status: approved, not implemented.

## Intent

A chat created with no project selected gets only `load_skill`, `web_search`, `fetch_url` and `lookup_paper` (`base_tool_definitions(false)` in `src-tauri/src/agent/mod.rs`). The persona prompts still tell the model to write `TASK.md` and use the Docket, so a small model plans around tools it does not have. A real run (chat `1a085b7c`, `gemma4:12b-mlx`) made 13 `sequentialthinking` calls, "simulated" `TASK.md`, and never read a page.

Give every chat without a project its own scratch folder, `~/.thea/chats/<chat-id>/`, so the persona's full workflow runs there.

## Goals

- A chat without a project runs with the persona's full tool set, rooted at `~/.thea/chats/<chat-id>/`.
- The Files and Artifacts pane shows that folder for the active chat.
- Deleting the chat deletes its folder.
- The Personal Assistant loads only its own skills and reads pages before it states facts.

## Non-goals

- Moving a chat into a project. Planned as a follow-up; the per-chat folder keeps everything a move needs in one place.
- One Docket shared across chats. Anything that should last belongs in a project.
- Database schema changes. `chats.project_id` stays `NULL` for these chats.

## Approaches

| Approach | Trade-off | Outcome |
|---|---|---|
| One folder per chat (`~/.thea/chats/<chat-id>/`) | No sharing between chats; nothing collides (`TASK.md`, approvals, Docket keys). Each chat has its own Docket. | Chosen. |
| One folder per persona (`~/.thea/workspaces/<persona>/`) | One lasting Docket, but `TASK.md` and its nudges leak between chats. | Rejected. |
| Keep the reduced tool set and fix only the prompt | Smallest change, but no Docket, drafts or `.ics` without a project. | Rejected. |

## Design

### 1. Scratch workspace (backend)

- In `run_agent_turn`, when `chat.project_id` is `None`, build an in-memory `Project` (not stored in the database): `id = "chat:<chat-id>"`, `root_path = thea_home_dir()/chats/<chat-id>`, `name = "Chat workspace"`, empty `instructions`, `persona_id` from the chat. Create the folder before the turn. All downstream code that takes `project: Option<&Project>` (tool execution, approvals keyed by project id, `TASK.md` nudges, rounds) then works unchanged.
- One helper resolves a workspace id to a `Project`: a real project from the database, or the stand-in for a `chat:<id>` id. `list_project_files` and `read_project_file` in `src-tauri/src/lib.rs` use it, so the Files pane can browse the chat folder.
- `delete_chat` also removes `~/.thea/chats/<chat-id>/` if it exists.
- `base_tool_definitions(false)` no longer has a caller in the agent path; remove it if nothing else uses it.

### 2. Files and Artifacts pane (frontend)

- With no active project and an active chat, the pane uses `chat:<chatId>` as the workspace id. Knowledge-file pinning stays project-only; hide it for a chat workspace.

### 3. Personal Assistant prompt and skills

- Set `skill_ids` for `personal-assistant` to its own skills plus the shared ones: `task-checklist`, `think-in-steps`, `manage-docket`, `draft-communication`, `weekly-review`, `write-ste`. This stops it loading `research-method`, which refers to `add_source` and `research/notes.md`.
- Add one rule to its system prompt: search once per option, and confirm facts such as visa rules, prices and dates on an official page with `fetch_url` before you state them.

## Left to the builder

- The exact helper name and where it lives (`db.rs` or `lib.rs`).
- Whether the stand-in id prefix is `chat:` or another string that cannot collide with a UUID project id.
- Tests: the stand-in `Project` for a chat without a project; `delete_chat` removes the folder; the files command resolves a `chat:` id; the Personal Assistant skill list excludes `research-method`.
