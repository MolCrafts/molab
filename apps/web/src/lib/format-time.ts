/**
 * Shared time formatters used across the app for run/execution rows,
 * scheduler dashboards, and other timeline views.
 */

import { formatDateTime } from "@/lib/datetime";

export const formatRelative = (iso: string | null): string => {
  if (!iso) return "—";
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return iso;
  const delta = (Date.now() - ts) / 1000;
  if (delta < 60) return "just now";
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
};

// One wall-clock spelling app-wide: delegate to the shared formatter instead
// of locale-dependent `toLocaleString()` (which rendered "02/07/2026, …" next
// to ISO strings elsewhere on the same screen).
export const formatTimestamp = (iso: string | null): string => formatDateTime(iso);

/** An ISO instant as epoch milliseconds; null when absent or unparseable. */
export const parseInstant = (value: string | null | undefined): number | null => {
  const parsed = value ? Date.parse(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
};
