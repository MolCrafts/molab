/**
 * Shell layout preferences (L00): which regions are open. Per-browser UI
 * state, persisted under one key; sizes persist through the panel groups'
 * own `autoSaveId` (`molab.shell.v3*`). Storage can be missing or throw
 * (private windows, blocked site data) — every access is guarded and the
 * shell renders from defaults without it.
 */

import { useCallback, useMemo, useState } from "react";

export const SHELL_STORAGE_KEY = "molab.shell.v3";
const LAYOUT_KEY = `${SHELL_STORAGE_KEY}.layout`;

export interface ShellLayout {
  sideBarVisible: boolean;
  panelVisible: boolean;
  pinnedExpanded: boolean;
}

export const DEFAULT_SHELL_LAYOUT: ShellLayout = {
  sideBarVisible: true,
  panelVisible: false,
  pinnedExpanded: false,
};

export const parseShellLayout = (raw: string | null): ShellLayout => {
  if (!raw) return DEFAULT_SHELL_LAYOUT;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return DEFAULT_SHELL_LAYOUT;
    const record = parsed as Record<string, unknown>;
    const flag = (key: keyof ShellLayout): boolean =>
      typeof record[key] === "boolean" ? (record[key] as boolean) : DEFAULT_SHELL_LAYOUT[key];
    return {
      sideBarVisible: flag("sideBarVisible"),
      panelVisible: flag("panelVisible"),
      pinnedExpanded: flag("pinnedExpanded"),
    };
  } catch {
    return DEFAULT_SHELL_LAYOUT;
  }
};

const readLayout = (): ShellLayout => {
  try {
    return parseShellLayout(window.localStorage.getItem(LAYOUT_KEY));
  } catch {
    return DEFAULT_SHELL_LAYOUT;
  }
};

const writeLayout = (layout: ShellLayout): void => {
  try {
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
  } catch {
    // Not persisted; the in-memory layout still applies for this session.
  }
};

export interface ShellLayoutControls extends ShellLayout {
  toggle: (key: keyof ShellLayout) => void;
  set: (key: keyof ShellLayout, value: boolean) => void;
}

export const useShellLayout = (): ShellLayoutControls => {
  const [layout, setLayout] = useState<ShellLayout>(readLayout);
  const set = useCallback((key: keyof ShellLayout, value: boolean) => {
    setLayout((current) => {
      if (current[key] === value) return current;
      const next = { ...current, [key]: value };
      writeLayout(next);
      return next;
    });
  }, []);
  const toggle = useCallback((key: keyof ShellLayout) => {
    setLayout((current) => {
      const next = { ...current, [key]: !current[key] };
      writeLayout(next);
      return next;
    });
  }, []);
  return useMemo(() => ({ ...layout, toggle, set }), [layout, toggle, set]);
};
