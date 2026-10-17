/**
 * Rewrite relative knowledge images onto ``GET /api/workspace/file/blob``.
 *
 * A document is a markdown file; figures sit next to it on the workspace
 * filesystem. The editor is an SPA, so ``![…](figs/a.png)`` would fetch
 * ``/figs/a.png`` from the UI origin and 404. Blob URLs are display-only:
 * {@link restoreKnowledgeMedia} turns them back into relative paths before save.
 */

export const KNOWLEDGE_BLOB_PATH = "/api/workspace/file/blob";

const IMAGE_MARKDOWN = /!\[([^\]]*)\]\((<)?([^)\s>]+)(>)?\)/g;

const PASSTHROUGH = /^(?:https?:|data:|\/api\/)/i;

export function knowledgeBlobUrl(workspaceRelPath: string): string {
  return `${KNOWLEDGE_BLOB_PATH}?path=${encodeURIComponent(workspaceRelPath)}`;
}

/** Resolve *src* against the document's workspace-relative path, or ``null``. */
export function resolveKnowledgeMediaPath(docRelPath: string, src: string): string | null {
  const trimmed = src.trim();
  if (!trimmed || trimmed.startsWith("#") || PASSTHROUGH.test(trimmed)) {
    return null;
  }
  try {
    const resolved = new URL(trimmed, `https://workspace.local/${docRelPath}`).pathname;
    const rel = decodeURIComponent(resolved.replace(/^\//, ""));
    if (!rel || rel.startsWith("..")) {
      return null;
    }
    return rel;
  } catch {
    return null;
  }
}

export function posixRelative(fromDir: string, toPath: string): string {
  const from = fromDir.split("/").filter(Boolean);
  const to = toPath.split("/").filter(Boolean);
  let i = 0;
  while (i < from.length && i < to.length && from[i] === to[i]) {
    i += 1;
  }
  const up = from.length - i;
  const down = to.slice(i);
  return [...Array.from({ length: up }, () => ".."), ...down].join("/") || ".";
}

/** ``<img src>`` for the editor: relative workspace path → blob URL, else unchanged. */
export function proxyKnowledgeImageUrl(docRelPath: string, src: string): string {
  const resolved = resolveKnowledgeMediaPath(docRelPath, src);
  return resolved ? knowledgeBlobUrl(resolved) : src;
}

/** Display form: relative ``![](figs/a.png)`` → blob URL the ``<img>`` can fetch. */
export function rewriteKnowledgeMedia(body: string, docRelPath: string): string {
  return body.replace(IMAGE_MARKDOWN, (full, alt: string, _open: string, src: string) => {
    const resolved = resolveKnowledgeMediaPath(docRelPath, src);
    if (!resolved) {
      return full;
    }
    return `![${alt}](<${knowledgeBlobUrl(resolved)}>)`;
  });
}

/** Persist form: blob URLs → paths relative to the document. */
export function restoreKnowledgeMedia(body: string, docRelPath: string): string {
  const fromDir = docRelPath.includes("/") ? docRelPath.slice(0, docRelPath.lastIndexOf("/")) : "";
  return body.replace(IMAGE_MARKDOWN, (full, alt: string, _open: string, src: string) => {
    const path = blobPathFromSrc(src);
    if (!path) {
      return full;
    }
    return `![${alt}](${posixRelative(fromDir, path)})`;
  });
}

function blobPathFromSrc(src: string): string | null {
  try {
    const url = new URL(src.trim(), "https://ui.local");
    if (url.pathname !== KNOWLEDGE_BLOB_PATH) {
      return null;
    }
    const path = url.searchParams.get("path");
    return path && !path.startsWith("..") ? path : null;
  } catch {
    return null;
  }
}
