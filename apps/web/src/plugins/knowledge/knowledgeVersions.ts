/**
 * Git versions of a knowledge document, as the server numbers them: v1 is the
 * first commit that wrote the file, vN the newest. A working file that differs
 * from vN is the uncommitted working copy, not a version.
 */

import type { DocumentHistory } from "@/api/generated/models/DocumentHistory";
import type { DocumentVersion } from "@/api/generated/models/DocumentVersion";

/** The commit's event in a word: `knowledge.rewritten` → "rewritten"; no trailer is a manual commit. */
export const versionEvent = (version: DocumentVersion): string =>
  version.event ? version.event.replace(/^knowledge\./, "").replaceAll("_", " ") : "manual commit";

/** Who made the commit, when molab recorded it. */
export const versionAgent = (version: DocumentVersion): string =>
  version.agent ? (version.agent.name ?? version.agent.id) : "";

/** The newest version's number, or null before the first commit. */
export const latestVersion = (history: DocumentHistory): number | null =>
  history.versions[0]?.number ?? null;

/**
 * The version to put in the URL when *number* is chosen: the newest version
 * of a clean file is the live page itself, which stays editable.
 */
export const versionToOpen = (history: DocumentHistory, number: number): number | null =>
  number === latestVersion(history) && !history.uncommitted ? null : number;

/** The switcher's label for what the page shows: an old version, the working copy, or the latest. */
export const versionSwitcherLabel = (history: DocumentHistory, viewing: number | null): string => {
  const latest = latestVersion(history);
  if (viewing !== null) return `v${viewing} of ${latest ?? viewing}`;
  if (history.uncommitted) return "Working copy";
  return `v${latest} · latest`;
};

export type DiffLineTone = "added" | "removed" | "hunk" | "context";

/** How a unified-diff line reads: the file headers are context, not changes. */
export const diffLineTone = (line: string): DiffLineTone => {
  if (line.startsWith("+++") || line.startsWith("---")) return "context";
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("+")) return "added";
  if (line.startsWith("-")) return "removed";
  return "context";
};
