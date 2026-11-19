import { describe, expect, it } from "vitest";
import { extractArtifactsFromMarkdown, inferLanguageFromPath } from "./artifacts";

describe("extractArtifactsFromMarkdown", () => {
  it("extracts HTML and multi-line code blocks", () => {
    const md = [
      "Here is a prototype:",
      "```html",
      "<!doctype html><html><head><title>Calc</title></head><body><h1>Hi</h1></body></html>",
      "```",
      "And a short one-liner:",
      "```bash",
      "npm install",
      "```",
    ].join("\n");

    const items = extractArtifactsFromMarkdown(md, "msg-1");
    expect(items).toHaveLength(1);
    expect(items[0].title).toBe("Calc");
    expect(items[0].language).toBe("html");
  });

  it("infers language from file extension", () => {
    expect(inferLanguageFromPath("src/App.tsx")).toBe("tsx");
    expect(inferLanguageFromPath("index.html")).toBe("html");
    expect(inferLanguageFromPath("main.py")).toBe("python");
  });
});
