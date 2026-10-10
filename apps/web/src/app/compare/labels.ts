/**
 * Naming runs that came from different places.
 *
 * Run names only have to be unique inside their experiment, so a set built
 * across projects collides constantly — every sweep has a `run-001`. A label
 * therefore has to carry enough of the run's parent entities to tell it apart,
 * and no more.
 *
 * These are entity names (run, experiment, project, workspace), never a
 * filesystem path. When a single string is required, parents join with a
 * middot; a slash would read as a path, which this UI does not show.
 *
 * The depth is chosen once for the whole set rather than per entry. A legend
 * where half the entries are `n=8` and the other half are four segments long
 * reads as two different kinds of thing; a uniform depth reads as a list.
 */

import { type CompareEntry, refKey } from "./types";

/** Parent entities of one entry, innermost first — the order labels grow outwards in. */
const labelLevels = (entry: CompareEntry): string[] => [
  entry.runName,
  entry.experimentName,
  entry.projectName,
  entry.workspaceLabel,
];

const MAX_DEPTH = 4;

/** Entity names, outermost first, joined as names rather than as a path. */
export const labelAtDepth = (entry: CompareEntry, depth: number): string => {
  const levels = labelLevels(entry).slice(0, Math.max(1, Math.min(depth, MAX_DEPTH)));
  return levels.reverse().join(" · ");
};

/**
 * Shallowest depth at which every entry gets a distinct label.
 *
 * Falls back to `MAX_DEPTH` when even the full ancestry collides — two entries
 * with identical names at every level are still distinct runs (their refs
 * differ), and a duplicated legend entry is better than an invented one.
 */
export const uniqueLabelDepth = (entries: readonly CompareEntry[]): number => {
  for (let depth = 1; depth < MAX_DEPTH; depth += 1) {
    const seen = new Set(entries.map((entry) => labelAtDepth(entry, depth)));
    if (seen.size === entries.length) return depth;
  }
  return MAX_DEPTH;
};

/** Parent entity that tells colliding run names apart; null when the run name is enough. */
export const disambiguator = (entry: CompareEntry, depth: number): string | null => {
  if (depth <= 1) return null;
  return labelLevels(entry)[Math.min(depth, MAX_DEPTH) - 1] || null;
};

/**
 * Label every entry at one uniform, shortest-sufficient depth.
 *
 * Keyed by `refKey` so callers can look a label up from a series id without
 * carrying the entry alongside it.
 */
export const shortestUniqueLabels = (entries: readonly CompareEntry[]): Map<string, string> => {
  const depth = uniqueLabelDepth(entries);
  const out = new Map<string, string>();
  for (const entry of entries) {
    out.set(refKey(entry.ref), labelAtDepth(entry, depth));
  }
  return out;
};
