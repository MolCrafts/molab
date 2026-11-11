/**
 * React side of the editor tabs: the open set follows navigation, persists per
 * served workspace, and closing / cycling navigate to the tab's last location.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { leftPanelViewFromPath, listAllNavigationContributions } from "@/app/navigation/sections";
import { buildSelectionFromLocation } from "@/app/state/useNavigationState";
import type { LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { describeEditorTab } from "./describeEditorTab";
import {
  addEditorTabInBackground,
  adjacentEditorTab,
  closeEditorTab,
  type EditorTab,
  type EditorTabsState,
  editorOpenMode,
  editorTabKey,
  followLocation,
  parseStoredEditorTabs,
  pinEditorTab,
} from "./editorTabs";
import { useTabSnapshot } from "./useTabSnapshot";

const STORAGE_PREFIX = "molab.editorTabs.v1";

const storageKey = (workspaceKey: string): string => `${STORAGE_PREFIX}:${workspaceKey}`;

const readTabs = (key: string): EditorTabsState => {
  try {
    return parseStoredEditorTabs(window.localStorage.getItem(key));
  } catch {
    return parseStoredEditorTabs(null);
  }
};

const writeTabs = (key: string, state: EditorTabsState): void => {
  try {
    window.localStorage.setItem(key, JSON.stringify(state));
  } catch {
    // The open set lives in memory for this session only.
  }
};

/** Where the editor goes when the last tab closes: a section with no page of its own. */
const emptyEditorRoute = (view: LeftPanelView): string => {
  const sections = listAllNavigationContributions();
  const current = sections.find((section) => section.id === view);
  if (current && !current.landing) return current.route;
  return sections.find((section) => section.id === "projects")?.route ?? "/projects";
};

export interface EditorTabsControls {
  state: EditorTabsState;
  /** Add a tab for `path` without leaving the current one. */
  openInBackground: (path: string) => void;
  activate: (key: string) => void;
  close: (key: string) => void;
  closeActive: () => void;
  /** Double-click an italic tab: it becomes concrete and stays put. */
  pin: (key: string) => void;
  cycle: (delta: number) => void;
}

export const useEditorTabs = (
  selection: Selection | null,
  leftPanelView: LeftPanelView,
  workspaceSnapshot: WorkspaceSnapshot,
): EditorTabsControls => {
  const snapshot = useTabSnapshot(workspaceSnapshot);
  const location = useLocation();
  const navigate = useNavigate();
  // One open set per served workspace, keyed by its stable key (not the
  // session's query-scope counter, which restarts on every load).
  const workspace =
    snapshot.workspaces.find((candidate) => candidate.active) ?? snapshot.workspaces[0];
  const key = storageKey(workspace?.key ?? "");
  const [loadedKey, setLoadedKey] = useState(key);
  const [state, setState] = useState<EditorTabsState>(() => readTabs(key));
  if (loadedKey !== key) {
    // The workspace became known (or changed): adopt its stored set.
    setLoadedKey(key);
    setState(readTabs(key));
  }
  /** The active tab asked to close; it goes once the URL has left it. */
  const pendingClose = useRef<string | null>(null);

  const section = listAllNavigationContributions().find(({ id }) => id === leftPanelView);
  const tabKey = editorTabKey(selection, {
    id: leftPanelView,
    hasLanding: Boolean(section?.landing),
  });
  const path = `${location.pathname}${location.search}`;
  const openMode = editorOpenMode(location.state);
  const kind: EditorTab["kind"] = selection ? selection.objectType : "section";
  const label = tabKey
    ? describeEditorTab({ key: tabKey, path, kind, label: selection?.objectId ?? "" }, snapshot)
        .label
    : "";

  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` re-runs this after the stored set is adopted
  useEffect(() => {
    const pending = pendingClose.current !== tabKey ? pendingClose.current : null;
    if (pending) pendingClose.current = null;
    const current = tabKey ? { key: tabKey, path, kind, label } : null;
    setState((previous) => followLocation(previous, current, pending, openMode));
  }, [key, tabKey, path, kind, label, openMode]);

  // Nothing is stored until a workspace is known: a set saved under no key
  // would be handed to whichever workspace loads next.
  const persistable = Boolean(workspace);
  useEffect(() => {
    if (persistable) writeTabs(key, state);
  }, [key, persistable, state]);

  const activate = useCallback(
    (target: string) => {
      const tab = state.tabs.find((candidate) => candidate.key === target);
      if (tab) navigate(tab.path);
    },
    [navigate, state.tabs],
  );

  const close = useCallback(
    (target: string) => {
      const result = closeEditorTab(state, target);
      if (result.state === state) return;
      if (state.activeKey !== target) {
        setState(result.state);
        return;
      }
      pendingClose.current = target;
      navigate(result.next ? result.next.path : emptyEditorRoute(leftPanelView));
    },
    [leftPanelView, navigate, state],
  );

  const pin = useCallback((target: string) => {
    setState((previous) => pinEditorTab(previous, target));
  }, []);

  const closeActive = useCallback(() => {
    if (state.activeKey) close(state.activeKey);
  }, [close, state.activeKey]);

  const cycle = useCallback(
    (delta: number) => {
      const next = adjacentEditorTab(state, delta);
      if (next) navigate(next.path);
    },
    [navigate, state],
  );

  const openInBackground = useCallback(
    (target: string) => {
      const url = new URL(target, window.location.origin);
      const opened = buildSelectionFromLocation(url.pathname, url.searchParams);
      const view = leftPanelViewFromPath(url.pathname);
      const landing = listAllNavigationContributions().find(({ id }) => id === view)?.landing;
      const openedKey = editorTabKey(opened, { id: view, hasLanding: Boolean(landing) });
      if (!openedKey) return;
      const openedKind: EditorTab["kind"] = opened ? opened.objectType : "section";
      const tab = {
        key: openedKey,
        path: `${url.pathname}${url.search}`,
        kind: openedKind,
        label: "",
      };
      const presented = describeEditorTab(tab, snapshot).label;
      setState((previous) => addEditorTabInBackground(previous, { ...tab, label: presented }));
    },
    [snapshot],
  );

  return { state, openInBackground, activate, close, closeActive, pin, cycle };
};
