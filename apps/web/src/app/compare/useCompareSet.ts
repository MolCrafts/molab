/**
 * The comparison bag — project / experiment / run items gathered to compare.
 *
 * Selection that lives in a table's `useState` cannot cross a project: the
 * moment you navigate away to find the second run, the first is gone. So the
 * bag is a module-level singleton, and it is persisted to `localStorage`.
 *
 * The bag itself is the selected set. Expanding to runs is a pure projection
 * (`expandToRuns`) and is never written back here.
 */

import { useMemo, useSyncExternalStore } from "react";

import { type CompareItem, type CompareRef, isDescendantRef, itemKey } from "./types";

export const STORAGE_KEY = "molab.selectionSet.v1";
const LEGACY_STORAGE_KEY = "molab.compareSet.v1";

export class SubtreeNotLoadedError extends Error {
  readonly ref: CompareRef;

  constructor(ref: CompareRef) {
    super(`Subtree for ${itemKey(ref)} is not loaded.`);
    this.name = "SubtreeNotLoadedError";
    this.ref = ref;
  }
}

export interface MergeBagContext {
  /** True when explorer snapshot has a complete child list for this ancestor. */
  isSubtreeLoaded: (ref: CompareRef) => boolean;
  /** Run-kind items for loaded children of `ancestor`, excluding `exceptKey`. */
  siblingRuns: (ancestor: CompareItem, exceptKey: string) => CompareItem[];
}

const emptyContext: MergeBagContext = {
  isSubtreeLoaded: () => false,
  siblingRuns: () => [],
};

const ancestorOf = (item: CompareRef, other: CompareRef): boolean => isDescendantRef(other, item);

/**
 * Append items that are not already present, applying ancestor/descendant
 * replacement. Re-adding a present item is a no-op rather than a move-to-end.
 */
export const mergeIntoBag = (
  current: readonly CompareItem[],
  incoming: readonly CompareItem[],
  ctx: MergeBagContext = emptyContext,
): CompareItem[] => {
  let next = current as CompareItem[];
  let changed = false;

  for (const item of incoming) {
    const key = itemKey(item.ref);
    const ancestor = next.find((row) => ancestorOf(row.ref, item.ref));
    if (ancestor) {
      if (!ctx.isSubtreeLoaded(ancestor.ref)) {
        throw new SubtreeNotLoadedError(ancestor.ref);
      }
      const siblings = ctx.siblingRuns(ancestor, key);
      next = [
        ...next.filter((row) => itemKey(row.ref) !== itemKey(ancestor.ref)),
        ...siblings.filter(
          (row) => !next.some((existing) => itemKey(existing.ref) === itemKey(row.ref)),
        ),
        item,
      ];
      changed = true;
      continue;
    }

    const withoutDescendants = next.filter((row) => !isDescendantRef(row.ref, item.ref));
    if (withoutDescendants.length !== next.length) {
      next = [...withoutDescendants, item];
      changed = true;
      continue;
    }

    if (next.some((row) => itemKey(row.ref) === key)) continue;
    next = [...next, item];
    changed = true;
  }

  return changed ? next : (current as CompareItem[]);
};

/** @deprecated Prefer mergeIntoBag — kept as an alias for run-only table adds. */
export const addEntries = (
  current: readonly CompareItem[],
  incoming: readonly CompareItem[],
  ctx?: MergeBagContext,
): CompareItem[] => mergeIntoBag(current, incoming, ctx);

export const removeEntry = (current: readonly CompareItem[], key: string): CompareItem[] => {
  const next = current.filter((entry) => itemKey(entry.ref) !== key);
  return next.length === current.length ? (current as CompareItem[]) : next;
};

export const reorderItems = (
  current: readonly CompareItem[],
  fromIndex: number,
  toIndex: number,
): CompareItem[] => {
  if (
    fromIndex === toIndex ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= current.length ||
    toIndex >= current.length
  ) {
    return current as CompareItem[];
  }
  const next = [...current];
  const [moved] = next.splice(fromIndex, 1);
  if (moved === undefined) return current as CompareItem[];
  next.splice(toIndex, 0, moved);
  return next;
};

export const setItemCategory = (
  current: readonly CompareItem[],
  key: string,
  category: string | null,
): CompareItem[] => {
  let changed = false;
  const next = current.map((entry) => {
    if (itemKey(entry.ref) !== key || entry.category === category) return entry;
    changed = true;
    return { ...entry, category };
  });
  return changed ? next : (current as CompareItem[]);
};

export const setEntryExecution = (
  current: readonly CompareItem[],
  key: string,
  executionId: string | null,
): CompareItem[] => {
  let changed = false;
  const next = current.map((entry) => {
    if (
      itemKey(entry.ref) !== key ||
      entry.ref.kind !== "run" ||
      entry.executionId === executionId
    ) {
      return entry;
    }
    changed = true;
    return { ...entry, executionId };
  });
  return changed ? next : (current as CompareItem[]);
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const parseRef = (value: unknown): CompareRef | null => {
  if (!isObject(value)) return null;
  const workspaceKey = value.workspaceKey;
  const projectId = value.projectId;
  if (typeof workspaceKey !== "string" || typeof projectId !== "string") return null;
  const kind = value.kind;
  if (kind === "project") return { kind, workspaceKey, projectId };
  if (kind === "experiment") {
    const experimentId = value.experimentId;
    if (typeof experimentId !== "string") return null;
    return { kind, workspaceKey, projectId, experimentId };
  }
  const experimentId = value.experimentId;
  const runId = value.runId;
  if (typeof experimentId !== "string" || typeof runId !== "string") return null;
  if (kind === "run" || kind === undefined) {
    return { kind: "run", workspaceKey, projectId, experimentId, runId };
  }
  return null;
};

const normalizeItem = (value: unknown): CompareItem | null => {
  if (!isObject(value)) return null;
  const ref = parseRef(value.ref);
  if (!ref) return null;
  return {
    ref,
    executionId:
      ref.kind === "run" && typeof value.executionId === "string" ? value.executionId : null,
    workspaceLabel:
      typeof value.workspaceLabel === "string" ? value.workspaceLabel : ref.workspaceKey,
    projectName: typeof value.projectName === "string" ? value.projectName : ref.projectId,
    experimentName:
      typeof value.experimentName === "string"
        ? value.experimentName
        : ref.kind === "project"
          ? ""
          : ref.experimentId,
    runName:
      typeof value.runName === "string" ? value.runName : ref.kind === "run" ? ref.runId : "",
    parameters:
      isObject(value.parameters) && !Array.isArray(value.parameters)
        ? (value.parameters as Record<string, unknown>)
        : {},
    category: typeof value.category === "string" && value.category !== "" ? value.category : null,
    addedAt: typeof value.addedAt === "string" ? value.addedAt : new Date(0).toISOString(),
  };
};

export const parseStoredEntries = (raw: string | null): CompareItem[] => {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalizeItem).filter((item): item is CompareItem => item !== null);
  } catch {
    return [];
  }
};

const readStorage = (): { items: CompareItem[]; migratedFromLegacy: boolean } => {
  try {
    const current = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (current) return { items: parseStoredEntries(current), migratedFromLegacy: false };
    const legacy = globalThis.localStorage?.getItem(LEGACY_STORAGE_KEY);
    if (!legacy) return { items: [], migratedFromLegacy: false };
    return { items: parseStoredEntries(legacy), migratedFromLegacy: true };
  } catch {
    return { items: [], migratedFromLegacy: false };
  }
};

const writeStorage = (items: readonly CompareItem[]): void => {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(items));
    globalThis.localStorage?.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // Quota or a blocked store: the in-memory set is still correct.
  }
};

const initial = readStorage();
let entries: CompareItem[] = initial.items;
if (initial.migratedFromLegacy) writeStorage(entries);

const subscribers = new Set<() => void>();

const commit = (next: CompareItem[]): void => {
  if (next === entries) return;
  entries = next;
  writeStorage(entries);
  for (const notify of subscribers) notify();
};

const subscribe = (listener: () => void): (() => void) => {
  subscribers.add(listener);
  return () => {
    subscribers.delete(listener);
  };
};

const getSnapshot = (): CompareItem[] => entries;

export const compareSet = {
  entries: getSnapshot,
  add: (...incoming: CompareItem[]): void => commit(mergeIntoBag(entries, incoming)),
  addMany: (incoming: readonly CompareItem[], ctx?: MergeBagContext): void =>
    commit(mergeIntoBag(entries, incoming, ctx)),
  remove: (key: string): void => commit(removeEntry(entries, key)),
  clear: (): void => commit([]),
  reorder: (fromIndex: number, toIndex: number): void =>
    commit(reorderItems(entries, fromIndex, toIndex)),
  setCategory: (key: string, category: string | null): void =>
    commit(setItemCategory(entries, key, category)),
  setExecution: (key: string, executionId: string | null): void =>
    commit(setEntryExecution(entries, key, executionId)),
  has: (key: string): boolean => entries.some((entry) => itemKey(entry.ref) === key),
};

export interface UseCompareSet {
  entries: CompareItem[];
  keys: Set<string>;
  count: number;
  add: (...incoming: CompareItem[]) => void;
  addMany: (incoming: readonly CompareItem[], ctx?: MergeBagContext) => void;
  remove: (key: string) => void;
  clear: () => void;
  reorder: (fromIndex: number, toIndex: number) => void;
  setCategory: (key: string, category: string | null) => void;
  setExecution: (key: string, executionId: string | null) => void;
  has: (key: string) => boolean;
}

export const useCompareSet = (): UseCompareSet => {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return useMemo(
    () => ({
      entries: current,
      keys: new Set(current.map((entry) => itemKey(entry.ref))),
      count: current.length,
      add: compareSet.add,
      addMany: compareSet.addMany,
      remove: compareSet.remove,
      clear: compareSet.clear,
      reorder: compareSet.reorder,
      setCategory: compareSet.setCategory,
      setExecution: compareSet.setExecution,
      has: compareSet.has,
    }),
    [current],
  );
};

export const __resetCompareSetForTesting = (): void => {
  entries = [];
  writeStorage(entries);
};
