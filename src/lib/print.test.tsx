import { describe, expect, it } from "vitest";
import { pdfName, printableHtml } from "./print";

const art = (language: string, content: string) => ({ id: "a", title: "T <1>", language, content });

describe("printableHtml", () => {
  it("renders Markdown, with raw HTML in it kept as text", () => {
    const html = printableHtml(
      art("markdown", "# Brief\n\n- one [S1]\n\n<img src=x onerror=alert(1)>"),
    );
    expect(html).toContain("<h1>Brief</h1>");
    expect(html).toContain("<li>one [S1]</li>");
    expect(html).not.toContain("<img");
    expect(html).toContain("<title>T &lt;1&gt;</title>");
  });

  it("names the PDF after the file, with no folder or extension", () => {
    const brief = { ...art("markdown", ""), sourcePath: "research/book/brief.md" };
    expect(pdfName(brief)).toBe("brief");
    expect(printableHtml(brief)).toContain("<title>brief</title>");
    expect(pdfName(art("html", ""))).toBe("T <1>");
  });

  it("escapes code and blocks network calls from HTML pages", () => {
    expect(printableHtml(art("python", "if a < b:"))).toContain("<pre>if a &lt; b:</pre>");
    expect(printableHtml(art("html", "<p>hi</p>"))).toMatch(/connect-src 'none'.*<p>hi<\/p>$/);
  });
});
