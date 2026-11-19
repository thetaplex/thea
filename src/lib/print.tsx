import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ArtifactItem } from "./artifacts";

// The print window runs the page's scripts (charts must draw), but it must not phone home.
export const PREVIEW_CSP =
  "<meta http-equiv=\"Content-Security-Policy\" content=\"connect-src 'none'; form-action 'none'\">";

const PAGE_CSS = `
  body { font-family: Georgia, "Iowan Old Style", serif; color: #222; max-width: 46rem;
         margin: 2rem auto; padding: 0 1.5rem; line-height: 1.55; }
  h1, h2, h3 { line-height: 1.25; break-after: avoid; }
  pre, code { font-family: Menlo, Consolas, monospace; font-size: 0.85em; }
  pre { white-space: pre-wrap; background: #f6f3ee; padding: 0.75rem; border-radius: 4px; }
  table { border-collapse: collapse; } th, td { border: 1px solid #ccc; padding: 0.3rem 0.5rem; }
  a { color: inherit; }
  @page { margin: 18mm; }`;

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function page(title: string, body: string): string {
  return `<!doctype html><html><head><meta charset="utf-8">${PREVIEW_CSP}<title>${escapeHtml(title)}</title><style>${PAGE_CSS}</style></head><body>${body}</body></html>`;
}

/** The PDF's file name without `.pdf`: the file's own name with no folder and no extension. */
export function pdfName(a: ArtifactItem): string {
  const base = (a.sourcePath ?? a.title).split(/[\\/]/).pop() ?? "";
  return base.replace(/\.[^.]+$/, "") || "artifact";
}

/** The artifact as one HTML page to print: HTML as written, Markdown rendered, code as text. */
export function printableHtml(a: ArtifactItem, content = a.content): string {
  if (a.language === "html") return PREVIEW_CSP + content;
  if (a.language === "svg") return page(pdfName(a), content);
  if (a.language === "markdown" || a.language === "md") {
    return page(
      pdfName(a),
      renderToStaticMarkup(<ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>),
    );
  }
  return page(pdfName(a), `<pre>${escapeHtml(content)}</pre>`);
}
