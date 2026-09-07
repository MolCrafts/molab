/**
 * The comparison set — runs the user has gathered to plot against each other.
 *
 * Selection that lives in a table's `useState` cannot cross a project: the
 * moment you navigate away to find the second run, the first is gone. So the
 * set is a module-level singleton, mirroring `app/runs/useWorkspaceRuns.ts`,
 * and it is persisted to `localStorage` so a reload does not discard an
 * afternoon of gathering.
 *
 * Adding a run costs nothing but a write here: no metrics are fetched until
 * the compare page is told to scan. The set is a *selection*, and reading a
 * dozen runs' metric files is a separate, explicit act.
 *
 * The transitions are pure functions over a plain array so they can be tested
 * under the node environment without React — the same split `nextSelection`
 * and `aggregateSeries` use.
 */

import { useMemo, useSyncExternalStore } from "react";

import { type CompareEntry, refKey } from "./types";

const STORAGE_KEY = "molexp.compareSet.v1";

// ---------------------------------------------------------------------------
// Pure transitions
// ---------------------------------------------------------------------------

/**
 * Append entries that are not already present, preserving insertion order.
 *
 * Re-adding a run is a no-op rather than a move-to-end: the user who ctrl-adds
 * a row they already picked meant "make sure this is in", not "reorder".
 */
export const addEntries = (
  current: readonly CompareEntry[],
  incoming: readonly CompareEntry[],
): CompareEntry[] => {
  const present = new Set(current.map((entry) => refKey(entry.ref)));
  const additions = incoming.filter((entry) => {
    const key = refKey(entry.ref);
    if (present.has(key)) return false;
    present.add(key);
    return true;
  });
  return additions.length === 0 ? (current as CompareEntry[]) : [...current, ...additions];
};

export const removeEntry = (current: readonly CompareEntry[], key: string): CompareEntry[] => {
  const next = current.filter((entry) => refKey(entry.ref) !== key);
  return next.length === current.length ? (current as CompareEntry[]) : next;
};

/** Toggle whether a staged run is part of the comparison. */
export const setEntrySelected = (
  current: readonly CompareEntry[],
  key: string,
  selected: boolean,
): CompareEntry[] => {
  let changed = false;
  const next = current.map((entry) => {
    if (refKey(entry.ref) !== key || entry.selected === selected) return entry;
    changed = true;
    return { ...entry, selected };
  });
  return changed ? next : (current as CompareEntry[]);
};

/**
 * Toggle a named subset in one move.
 *
 * Ticking a project means ticking everything under it, and doing that one
 * `setEntrySelected` at a time would write the set to `localStorage` and
 * re-render every subscriber once per run in it.
 */
export const setEntriesSelected = (
  current: readonly CompareEntry[],
  keys: ReadonlySet<string>,
  selected: boolean,
): CompareEntry[] => {
  let changed = false;
  const next = current.map((entry) => {
    if (!keys.has(refKey(entry.ref)) || entry.selected === selected) return entry;
    changed = true;
    return { ...entry, selected };
  });
  return changed ? next : (current as CompareEntry[]);
};

/** Select or clear the whole set in one move. */
export const setAllSelected = (
  current: readonly CompareEntry[],
  selected: boolean,
): CompareEntry[] => {
  if (current.every((entry) => entry.selected === selected)) return current as CompareEntry[];
  return current.map((entry) => (entry.selected === selected ? entry : { ...entry, selected }));
};

/** Pin one entry to a specific attempt; `null` restores "latest". */
export const setEntryExecution = (
  current: readonly CompareEntry[],
  key: string,
  executionId: string | null,
): CompareEntry[] => {
  let changed = false;
  const next = current.map((entry) => {
    if (refKey(entry.ref) !== key || entry.executionId === executionId) return entry;
    changed = true;
    return { ...entry, executionId };
  });
  return changed ? next : (current as CompareEntry[]);
};

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

const isEntry = (value: unknown): value is CompareEntry => {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<CompareEntry>;
  const ref = entry.ref;
  if (typeof ref !== "object" || ref === null) return false;
  return (
    typeof ref.workspaceKey === "string" &&
    typeof ref.projectId === "string" &&
    typeof ref.experimentId === "string" &&
    typeof ref.runId === "string"
  );
};

/**
 * Read the persisted set, discarding anything that no longer parses.
 *
 * A stored set outlives the shape that wrote it, so a malformed entry is
 * dropped rather than thrown — losing one chip beats an unmountable shell.
 */
export const parseStoredEntries = (raw: string | null): CompareEntry[] => {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isEntry).map((entry) => ({
      ...entry,
      selected: entry.selected ?? true,
      executionId: entry.executionId ?? null,
      parameters: entry.parameters ?? {},
      workspaceLabel: entry.workspaceLabel ?? entry.ref.workspaceKey,
      projectName: entry.projectName ?? entry.ref.projectId,
      experimentName: entry.experimentName ?? entry.ref.experimentId,
      runName: entry.runName ?? entry.ref.runId,
      addedAt: entry.addedAt ?? new Date(0).toISOString(),
    }));
  } catch {
    return [];
  }
};

// `localStorage` is absent under the node test environment and can throw in a
// browser with site data blocked; neither is a reason for the set to fail.
const readStorage = (): string | null => {
  try {
    return globalThis.localStorage?.getItem(STORAGE_KEY) ?? null;
  } catch {
    return null;
  }
};

const writeStorage = (entries: readonly CompareEntry[]): void => {
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Quota or a blocked store: the in-memory set is still correct.
  }
};

// ---------------------------------------------------------------------------
// Singleton store
// ---------------------------------------------------------------------------

let entries: CompareEntry[] = parseStoredEntries(readStorage());
const subscribers = new Set<() => void>();

const commit = (next: CompareEntry[]): void => {
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

const getSnapshot = (): CompareEntry[] => entries;

export const compareSet = {
  entries: getSnapshot,
  add: (...incoming: CompareEntry[]): void => commit(addEntries(entries, incoming)),
  addMany: (incoming: readonly CompareEntry[]): void => commit(addEntries(entries, incoming)),
  remove: (key: string): void => commit(removeEntry(entries, key)),
  clear: (): void => commit([]),
  setExecution: (key: string, executionId: string | null): void =>
    commit(setEntryExecution(entries, key, executionId)),
  setSelected: (key: string, selected: boolean): void =>
    commit(setEntrySelected(entries, key, selected)),
  setManySelected: (keys: ReadonlySet<string>, selected: boolean): void =>
    commit(setEntriesSelected(entries, keys, selected)),
  setAllSelected: (selected: boolean): void => commit(setAllSelected(entries, selected)),
  has: (key: string): boolean => entries.some((entry) => refKey(entry.ref) === key),
};

export interface UseCompareSet {
  /** Everything staged for comparison. */
  entries: CompareEntry[];
  /** The subset currently ticked — what the comparison actually shows. */
  selected: CompareEntry[];
  keys: Set<string>;
  count: number;
  add: (...incoming: CompareEntry[]) => void;
  addMany: (incoming: readonly CompareEntry[]) => void;
  remove: (key: string) => void;
  clear: () => void;
  setExecution: (key: string, executionId: string | null) => void;
  setSelected: (key: string, selected: boolean) => void;
  setManySelected: (keys: ReadonlySet<string>, selected: boolean) => void;
  setAllSelected: (selected: boolean) => void;
  has: (key: string) => boolean;
}

/** Subscribe a component to the comparison set. */
export const useCompareSet = (): UseCompareSet => {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  // Memoised on the snapshot identity: the store hands back the same array
  // until it actually changes, so a consumer may use `keys` as an effect
  // dependency without re-running on every render.
  return useMemo(
    () => ({
      entries: current,
      selected: current.filter((entry) => entry.selected),
      keys: new Set(current.map((entry) => refKey(entry.ref))),
      count: current.length,
      add: compareSet.add,
      addMany: compareSet.addMany,
      remove: compareSet.remove,
      clear: compareSet.clear,
      setExecution: compareSet.setExecution,
      setSelected: compareSet.setSelected,
      setManySelected: compareSet.setManySelected,
      setAllSelected: compareSet.setAllSelected,
      has: compareSet.has,
    }),
    [current],
  );
};

/** Test-only reset; the singleton otherwise leaks state between cases. */
export const __resetCompareSetForTesting = (): void => {
  entries = [];
  writeStorage(entries);
};
