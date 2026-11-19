import { describe, expect, it } from "vitest";
import type { AppSettings } from "./ipc";
import { hasUnsavedKey } from "./providerKeys";

const withKey = (api_key: string) =>
  ({ provider_configs: { openrouter: { base_url: "u", api_key } } }) as unknown as AppSettings;

describe("hasUnsavedKey", () => {
  it("flags a typed key that was never saved", () => {
    expect(hasUnsavedKey(withKey("sk-or-1"), withKey(""))).toBe(true);
    expect(hasUnsavedKey(withKey("sk-or-1"), null)).toBe(true);
  });
  it("ignores a saved key and surrounding whitespace", () => {
    expect(hasUnsavedKey(withKey("sk-or-1 "), withKey("sk-or-1"))).toBe(false);
    expect(hasUnsavedKey(withKey(""), withKey(""))).toBe(false);
  });
});
