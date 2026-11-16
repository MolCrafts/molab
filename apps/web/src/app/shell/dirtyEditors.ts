// ─────────────────────────────────────────────────────────────────────────────
// Which editors hold unsaved edits (L06): a view with a draft marks its page's
// base path, and the editor tab whose path sits under it shows ● in place of ✕,
// as VS Code does. A tiny external store, so a deep view can mark it without
// threading props through the shell.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useSyncExternalStore } from "react";

let dirty: ReadonlySet<string> = new Set();
const listeners = new Set<() => void>();

const emit = (): void => {
  for (const listener of listeners) listener();
};

export const setEditorDirty = (base: string, on: boolean): void => {
  if (dirty.has(base) === on) return;
  const next = new Set(dirty);
  if (on) next.add(base);
  else next.delete(base);
  dirty = next;
  emit();
};

const subscribe = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const useDirtyEditors = (): ReadonlySet<string> =>
  useSyncExternalStore(
    subscribe,
    () => dirty,
    () => dirty,
  );

/** Same pathname, and the mark's first parameter has the same value (decoded). */
const sameQueryEditor = (mark: string, path: string): boolean => {
  const [markPath = "", markQuery = ""] = mark.split("?");
  const [tabPath = "", tabQuery = ""] = path.split("?");
  if (markPath !== tabPath) return false;
  const first = [...new URLSearchParams(markQuery)][0];
  if (!first) return false;
  return new URLSearchParams(tabQuery).get(first[0]) === first[1];
};

/**
 * The tab at `path` is dirty when a marked base is the path or one of its
 * ancestors. A mark with a query (`/workspace?file=a.md`) names one editor of
 * a page that shows many (files): it matches on that parameter's decoded value.
 */
export const isEditorDirty = (marked: ReadonlySet<string>, path: string): boolean => {
  const bare = path.split("?")[0] ?? path;
  for (const base of marked) {
    if (base.includes("?")) {
      if (sameQueryEditor(base, path)) return true;
      continue;
    }
    if (bare === base || bare.startsWith(`${base}/`)) return true;
  }
  return false;
};

/** The dirty mark of one workspace file's editor (L07). */
export const fileEditorMark = (filePath: string): string =>
  `/workspace?${new URLSearchParams({ file: filePath })}`;

/** Mark `base` dirty while `on`; unmarks when the view unmounts. */
export const useMarkEditorDirty = (base: string | null, on: boolean): void => {
  useEffect(() => {
    if (!base) return;
    setEditorDirty(base, on);
    return () => setEditorDirty(base, false);
  }, [base, on]);
};
