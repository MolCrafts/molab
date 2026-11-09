/**
 * Editor tabs — the open set of the editor area (L00).
 *
 * The URL addresses the active tab only; the open set is per-browser UI
 * state. A tab names an *entity* (or a section page), never a view of it, so
 * switching Overview → Logs updates the tab's path instead of opening a
 * second tab. Pure functions; `useEditorTabs` owns the React side.
 */

import type { LeftPanelView, Selection } from "@/app/types";

export type EditorTabKind = Selection["objectType"] | "section";

export interface EditorTab {
  /** Identity of what the tab shows (`run:<id>`, `section:runs`, …). */
  key: string;
  /** Last location of the tab, pathname + search; reopening restores the view. */
  path: string;
  kind: EditorTabKind;
  /** Label at the last sighting; the strip prefers a live label when it has one. */
  label: string;
}

export interface EditorTabsState {
  tabs: readonly EditorTab[];
  activeKey: string | null;
}

export const EMPTY_EDITOR_TABS: EditorTabsState = { tabs: [], activeKey: null };

/** Bound on the open set: an unbounded row only ever grows in a long session. */
export const MAX_EDITOR_TABS = 16;

export interface EditorSection {
  id: LeftPanelView;
  /** Whether the section owns a page of its own (Dashboard, Runs, Settings…). */
  hasLanding: boolean;
}

export const editorTabKey = (
  selection: Selection | null,
  section: EditorSection | null,
): string | null => {
  if (selection) {
    switch (selection.objectType) {
      case "task":
        return `task:${selection.runId}/${selection.taskId}`;
      case "workflow":
        return `workflow:${selection.workflowId}`;
      case "workspace-file":
        return `file:${selection.filePath}`;
      default:
        return `${selection.objectType}:${selection.objectId}`;
    }
  }
  return section?.hasLanding ? `section:${section.id}` : null;
};

const sameTab = (left: EditorTab, right: EditorTab): boolean =>
  left.key === right.key &&
  left.path === right.path &&
  left.kind === right.kind &&
  left.label === right.label;

export const openEditorTab = (state: EditorTabsState, tab: EditorTab): EditorTabsState => {
  const index = state.tabs.findIndex((candidate) => candidate.key === tab.key);
  if (index >= 0) {
    const current = state.tabs[index];
    if (current && sameTab(current, tab) && state.activeKey === tab.key) return state;
    return {
      tabs: state.tabs.map((candidate, i) => (i === index ? tab : candidate)),
      activeKey: tab.key,
    };
  }
  const activeIndex = state.tabs.findIndex((candidate) => candidate.key === state.activeKey);
  const insertAt = activeIndex >= 0 ? activeIndex + 1 : state.tabs.length;
  let tabs = [...state.tabs.slice(0, insertAt), tab, ...state.tabs.slice(insertAt)];
  if (tabs.length > MAX_EDITOR_TABS) {
    const evict = tabs.findIndex(
      (candidate) => candidate.key !== tab.key && candidate.key !== state.activeKey,
    );
    tabs = tabs.filter((_, i) => i !== evict);
  }
  return { tabs, activeKey: tab.key };
};

export interface CloseResult {
  state: EditorTabsState;
  /** The tab to navigate to — only when the active tab closed and one remains. */
  next: EditorTab | null;
}

export const closeEditorTab = (state: EditorTabsState, key: string): CloseResult => {
  const index = state.tabs.findIndex((candidate) => candidate.key === key);
  if (index < 0) return { state, next: null };
  const tabs = state.tabs.filter((_, i) => i !== index);
  if (tabs.length === 0) return { state: EMPTY_EDITOR_TABS, next: null };
  if (state.activeKey !== key) return { state: { tabs, activeKey: state.activeKey }, next: null };
  const next = tabs[Math.min(index, tabs.length - 1)] ?? null;
  return { state: { tabs, activeKey: next?.key ?? null }, next };
};

/**
 * Open a tab without leaving the current one (⌘-click, "Open in background"):
 * inserted after the active tab, the active tab unchanged; an open tab stays put.
 */
export const addEditorTabInBackground = (
  state: EditorTabsState,
  tab: EditorTab,
): EditorTabsState => {
  if (state.tabs.some((candidate) => candidate.key === tab.key)) return state;
  const opened = openEditorTab(state, tab);
  return { ...opened, activeKey: state.activeKey };
};

/** The tab `delta` steps from the active one, wrapping; the first when none is active. */
export const adjacentEditorTab = (state: EditorTabsState, delta: number): EditorTab | null => {
  const count = state.tabs.length;
  if (count === 0) return null;
  const index = state.tabs.findIndex((candidate) => candidate.key === state.activeKey);
  if (index < 0) return state.tabs[0] ?? null;
  return state.tabs[(((index + delta) % count) + count) % count] ?? null;
};

const TAB_KINDS: ReadonlySet<string> = new Set<EditorTabKind>([
  "section",
  "project",
  "experiment",
  "run",
  "task",
  "workflow",
  "asset",
  "knowledge",
  "workspace-file",
]);

const isEditorTab = (value: unknown): value is EditorTab => {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.key === "string" &&
    candidate.key.length > 0 &&
    typeof candidate.path === "string" &&
    candidate.path.startsWith("/") &&
    typeof candidate.kind === "string" &&
    TAB_KINDS.has(candidate.kind) &&
    typeof candidate.label === "string"
  );
};

/** Storage is untrusted: keep the well-formed tabs, never throw. */
export const parseStoredEditorTabs = (raw: string | null): EditorTabsState => {
  if (!raw) return EMPTY_EDITOR_TABS;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return EMPTY_EDITOR_TABS;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return EMPTY_EDITOR_TABS;
  }
  const record = parsed as Record<string, unknown>;
  const tabs = Array.isArray(record.tabs)
    ? record.tabs.filter(isEditorTab).slice(0, MAX_EDITOR_TABS)
    : [];
  const activeKey =
    typeof record.activeKey === "string" && tabs.some((t) => t.key === record.activeKey)
      ? record.activeKey
      : null;
  return { tabs, activeKey };
};

/**
 * The open set once the editor has arrived at `current` (null: nothing open).
 * Closing the active tab only *requests* the close and navigates; it lands
 * here when the URL has actually left that tab. A blocked navigation (unsaved
 * edits, "stay") therefore keeps the tab, its strip entry and its content in
 * step instead of dropping the tab while its page is still on screen.
 */
export const followLocation = (
  state: EditorTabsState,
  current: EditorTab | null,
  pendingClose: string | null,
): EditorTabsState => {
  const base =
    pendingClose && pendingClose !== current?.key
      ? closeEditorTab(state, pendingClose).state
      : state;
  if (current) return openEditorTab(base, current);
  return base.activeKey === null ? base : { ...base, activeKey: null };
};
