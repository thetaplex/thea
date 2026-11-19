export interface ArtifactItem {
  id: string;
  title: string;
  language: string;
  content: string;
  sourcePath?: string;
}

/**
 * Extracts fenced code blocks (```html, ```tsx, ```python, etc.) from markdown
 * so any substantive block (>= 4 lines or HTML/SVG) can be opened in the Artifacts pane.
 */
export function extractArtifactsFromMarkdown(markdown: string, messageId: string): ArtifactItem[] {
  const artifacts: ArtifactItem[] = [];
  const fenceRegex = /```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g;
  let index = 0;

  for (const match of markdown.matchAll(fenceRegex)) {
    const lang = (match[1] || "text").toLowerCase();
    const code = match[2].trim();
    const lines = code.split("\n").length;
    const isPreviewable = lang === "html" || lang === "svg" || lang === "markdown" || lang === "md";
    if (!isPreviewable && lines < 4) {
      continue;
    }
    index += 1;
    const title = inferTitle(code, lang, index);
    artifacts.push({
      id: `${messageId}-artifact-${index}`,
      title,
      language: lang,
      content: code,
    });
  }

  return artifacts;
}

function inferTitle(code: string, lang: string, index: number): string {
  const titleMatch = code.match(/<title>([^<]+)<\/title>/i);
  if (titleMatch) return titleMatch[1].trim();
  const headingMatch = code.match(/^#\s+(.+)$/m);
  if (headingMatch) return headingMatch[1].trim();
  const fnMatch = code.match(
    /(?:function|class|def|export\s+default\s+function)\s+([A-Za-z0-9_]+)/,
  );
  if (fnMatch) return `${fnMatch[1]} (${lang})`;
  return `${lang.toUpperCase()} Snippet #${index}`;
}

export function inferLanguageFromPath(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    html: "html",
    htm: "html",
    svg: "svg",
    md: "markdown",
    ts: "typescript",
    tsx: "tsx",
    js: "javascript",
    jsx: "jsx",
    py: "python",
    rs: "rust",
    json: "json",
    css: "css",
    sh: "bash",
    toml: "toml",
    yaml: "yaml",
    yml: "yaml",
  };
  return map[ext] || "text";
}
