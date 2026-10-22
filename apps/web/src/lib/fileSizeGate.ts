/**
 * Decide how much of a workspace file a viewer may pull down.
 *
 * Text viewers used to request whole files regardless of size, so opening a
 * multi-gigabyte trajectory or a long-running log meant the server read it all
 * into memory, shipped it, and the browser tried to render it. Every viewer now
 * consults this first, using the `sizeBytes` the file tree already carries, and
 * only fetches what it can actually display.
 *
 * The decision is a pure function of the size so it can be unit-tested and so
 * the same threshold applies everywhere; the viewers own the presentation.
 */

import type { WorkspaceTreeNode } from "@/app/types";
import { formatBytes } from "@/lib/format-bytes";

/** Largest file a viewer will load in full without being asked twice (2 MiB). */
export const FULL_LOAD_MAX_BYTES = 2 * 1024 * 1024;

/**
 * How much of an oversized file to request when the user asks to see it.
 *
 * Kept below {@link FULL_LOAD_MAX_BYTES} so a "load anyway" on a huge file is
 * still a bounded request. Consumed as the `maxBytes` of a text window once the
 * windowed endpoints are wired through the generated client.
 */
export const WINDOW_BYTES = 256 * 1024;

export type FileSizeDecision =
  /** Small enough to fetch whole. */
  | { kind: "full" }
  /** Too large to fetch whole; show a notice and offer a bounded window. */
  | { kind: "oversized"; sizeBytes: number; sizeLabel: string; windowBytes: number }
  /** Size unknown (the tree had no entry) — fetch and let the server cap it. */
  | { kind: "unknown" };

/**
 * Classify a file by size.
 *
 * @param sizeBytes Size from the file tree; `null`/`undefined` when unknown.
 * @returns What the viewer should do before issuing a request.
 */
export const fileSizeGate = (sizeBytes: number | null | undefined): FileSizeDecision => {
  if (sizeBytes == null || !Number.isFinite(sizeBytes) || sizeBytes < 0) {
    return { kind: "unknown" };
  }
  if (sizeBytes <= FULL_LOAD_MAX_BYTES) return { kind: "full" };
  return {
    kind: "oversized",
    sizeBytes,
    sizeLabel: formatBytes(sizeBytes),
    windowBytes: WINDOW_BYTES,
  };
};

/** True when the viewer may fetch without an explicit confirmation. */
export const canAutoLoad = (sizeBytes: number | null | undefined): boolean =>
  fileSizeGate(sizeBytes).kind !== "oversized";

/**
 * A bounded slice of a text file.
 *
 * Today every caller passes `undefined` and the server returns the whole file
 * (capped at its own limit). The windowed endpoints accept `mode`/`maxBytes`/
 * `sinceOffset`; this is the seam those params land on, so wiring them is a
 * change here rather than in each of the six viewers.
 */
export interface TextWindowRequest {
  /** Which end of the file to read — logs want the tail, sources the head. */
  mode: "head" | "tail";
  /** Maximum bytes to return. */
  maxBytes: number;
  /** Byte offset to continue from, for incremental follow. */
  sinceOffset?: number;
}

/** The window a viewer should request for an oversized file, or `undefined`. */
export const windowForDecision = (
  decision: FileSizeDecision,
  mode: "head" | "tail" = "head",
): TextWindowRequest | undefined =>
  decision.kind === "oversized" ? { mode, maxBytes: decision.windowBytes } : undefined;

/**
 * Size of a workspace file according to the already-loaded file tree.
 *
 * The viewers receive a path, not a tree node, and the tree is the only place
 * the size is known without asking the server — which is the request we are
 * trying to avoid making. Returns `null` when the path is not in the loaded
 * tree (an un-expanded branch), which the gate treats as "unknown".
 *
 * @param root Workspace tree root, or `null` before it loads.
 * @param path Workspace-relative file path.
 */
export const treeFileSize = (root: WorkspaceTreeNode | null, path: string): number | null => {
  if (!root) return null;
  const stack: WorkspaceTreeNode[] = [root];
  while (stack.length > 0) {
    const node = stack.pop();
    if (!node) continue;
    if (node.path === path) return node.kind === "file" ? node.sizeBytes : null;
    // Only descend where the path could live; the tree is wide.
    for (const child of node.children) {
      if (path === child.path || path.startsWith(`${child.path}/`)) stack.push(child);
    }
  }
  return null;
};
