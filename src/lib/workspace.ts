/** Workspace the Files pane shows: the project, else the chat's scratch folder (`chat:<id>`). */
export function workspaceId(projectId: string | null, chatId: string | null): string | null {
  return projectId ?? (chatId ? `chat:${chatId}` : null);
}

/** Whether a tool event from `eventChatId` belongs to the workspace on screen. */
export function eventInWorkspace(
  eventChatId: string,
  projectId: string | null,
  chatId: string | null,
  projectChatIds: string[],
): boolean {
  return eventChatId === chatId || (projectId !== null && projectChatIds.includes(eventChatId));
}

// Same ids as builtin_persona_ids() in src-tauri/src/db.rs. Neither writes code, so a new
// project for them is empty or an existing folder, never a code template.
const BUILTIN_PERSONA_IDS = ["personal-assistant", "research-assistant"];

/** The templates the new-project dialog offers for a persona. */
export function templatesFor<T extends { id: string }>(personaId: string, templates: T[]): T[] {
  return BUILTIN_PERSONA_IDS.includes(personaId)
    ? templates.filter((t) => t.id === "empty")
    : templates;
}
