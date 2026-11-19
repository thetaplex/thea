import { describe, expect, it } from "vitest";
import type { SkillInfo } from "./ipc";
import { customSkills } from "./skills";

const mk = (name: string, source: SkillInfo["source"]): SkillInfo =>
  ({ name, source, description: "", body: "", enabled: true, path: "" }) as SkillInfo;

describe("customSkills", () => {
  it("hides built-ins and keeps a custom skill that shadows one", () => {
    const out = customSkills([
      mk("write-ste", "builtin"),
      mk("write-ste", "global"),
      mk("mine", "project"),
    ]);
    expect(out.map((s) => `${s.name}:${s.source}`)).toEqual(["write-ste:global", "mine:project"]);
  });
});
