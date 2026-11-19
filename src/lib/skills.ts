import type { SkillInfo } from "./ipc";

/** Skills shown in the Skills pane and Settings: built-ins stay loadable but are not listed. */
export const customSkills = (skills: SkillInfo[]): SkillInfo[] =>
  skills.filter((s) => s.source !== "builtin");
