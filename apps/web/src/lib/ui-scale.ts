/**
 * Text size preference for the whole UI.
 *
 * Every type, spacing, and control token is in `rem`, so one root font size
 * scales the interface uniformly. The choice lives in localStorage (it is a
 * per-viewer reading preference, not workspace state) and is applied to
 * `<html>` before the first render so the page never flashes at the old size.
 */

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "molab.ui.text-scale";

export interface TextScaleOption {
  id: string;
  label: string;
  /** Root font size as a percentage of the browser default (16px). */
  percent: number;
}

export const TEXT_SCALES: readonly TextScaleOption[] = [
  { id: "compact", label: "Compact", percent: 100 },
  { id: "default", label: "Default", percent: 112.5 },
  { id: "large", label: "Large", percent: 125 },
  { id: "larger", label: "Larger", percent: 137.5 },
  { id: "largest", label: "Largest", percent: 150 },
];

export const DEFAULT_TEXT_SCALE = "default";

const subscribers = new Set<() => void>();

const isKnown = (id: string | null): id is string =>
  id !== null && TEXT_SCALES.some((option) => option.id === id);

const load = (): string => {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isKnown(stored) ? stored : DEFAULT_TEXT_SCALE;
  } catch {
    return DEFAULT_TEXT_SCALE;
  }
};

let current: string = typeof window === "undefined" ? DEFAULT_TEXT_SCALE : load();

const percentOf = (id: string): number =>
  TEXT_SCALES.find((option) => option.id === id)?.percent ?? 112.5;

/** Set `<html>` font size from the stored choice. Call once before rendering. */
export const applyTextScale = (id: string = current): void => {
  if (typeof document === "undefined") return;
  document.documentElement.style.fontSize = `${percentOf(id)}%`;
};

export const setTextScale = (id: string): void => {
  if (!isKnown(id) || id === current) return;
  current = id;
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Private mode / quota: keep the choice for this tab only.
  }
  applyTextScale(id);
  for (const fn of subscribers) fn();
};

const subscribe = (fn: () => void): (() => void) => {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
};

export const useTextScale = (): string =>
  useSyncExternalStore(
    subscribe,
    () => current,
    () => DEFAULT_TEXT_SCALE,
  );
