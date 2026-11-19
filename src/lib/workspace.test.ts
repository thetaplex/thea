import { describe, expect, it } from "vitest";
import { eventInWorkspace, templatesFor, workspaceId } from "./workspace";

describe("workspaceId", () => {
  it("prefers the project", () => expect(workspaceId("p1", "c1")).toBe("p1"));
  it("falls back to the chat workspace", () => expect(workspaceId(null, "c1")).toBe("chat:c1"));
  it("is null with neither", () => expect(workspaceId(null, null)).toBeNull());
});

describe("eventInWorkspace", () => {
  it("accepts the active chat", () => expect(eventInWorkspace("c1", null, "c1", [])).toBe(true));
  it("rejects another chat without a project", () =>
    expect(eventInWorkspace("c2", null, "c1", ["c1", "c2"])).toBe(false));
  it("accepts a sibling chat in the same project", () =>
    expect(eventInWorkspace("c2", "p1", "c1", ["c1", "c2"])).toBe(true));
  it("rejects a chat from another project", () =>
    expect(eventInWorkspace("c9", "p1", "c1", ["c1", "c2"])).toBe(false));
});

describe("templatesFor", () => {
  const all = [{ id: "empty" }, { id: "react-vite" }, { id: "static-html" }];
  it("offers only the empty project to the built-in personas", () => {
    expect(templatesFor("personal-assistant", all)).toEqual([{ id: "empty" }]);
    expect(templatesFor("research-assistant", all)).toEqual([{ id: "empty" }]);
  });
  it("offers every template to a custom persona", () =>
    expect(templatesFor("custom-abc", all)).toEqual(all));
});
