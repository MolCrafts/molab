/** Per-browser workbench theme, applied before rendering to avoid a color flash. */
import { useSyncExternalStore } from "react";

const STORAGE_KEY = "molab.ui.theme";
export type UiTheme = "light" | "dark";
const subscribers = new Set<() => void>();
let current: UiTheme = "light";

export const applyUiTheme = (): void => {
  if (typeof document === "undefined") return;
  try {
    current = window.localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    // Storage can be unavailable; the default remains usable for this tab.
  }
  document.documentElement.classList.toggle("dark", current === "dark");
};

export const setUiTheme = (theme: UiTheme): void => {
  if (theme === current) return;
  current = theme;
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Keep the selected theme for this tab when persistence is unavailable.
  }
  for (const notify of subscribers) notify();
};

const subscribe = (notify: () => void): (() => void) => {
  subscribers.add(notify);
  return () => subscribers.delete(notify);
};

export const useUiTheme = (): UiTheme =>
  useSyncExternalStore(
    subscribe,
    () => current,
    () => "light",
  );
