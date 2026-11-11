/**
 * Choosing what a colour means on a cross-scope chart.
 *
 * With one run per colour, twenty runs is twenty legend entries and no
 * readable signal. The useful question is usually "did the experiments differ"
 * or "did the seed matter" — so the user picks a grouping, runs sharing a
 * group value get one colour and one legend entry, and molplot's `detail`
 * channel still draws every run as its own curve.
 */

import { shortestUniqueLabels } from "./labels";
import { type CompareEntry, refKey } from "./types";

/** `run` labels each run individually; anything else is a shared group. */
export type ColorBy =
  | { kind: "run" }
  | { kind: "experiment" }
  | { kind: "project" }
  | { kind: "workspace" }
  | { kind: "parameter"; name: string };

const COLOR_BY_RUN: ColorBy = { kind: "run" };

/** Serialised form, for the select control and the URL. */
export const colorByToValue = (colorBy: ColorBy): string =>
  colorBy.kind === "parameter" ? `param:${colorBy.name}` : colorBy.kind;

export const colorByFromValue = (value: string): ColorBy =>
  value.startsWith("param:")
    ? { kind: "parameter", name: value.slice("param:".length) }
    : value === "experiment" || value === "project" || value === "workspace"
      ? { kind: value }
      : COLOR_BY_RUN;

/** Parameter names present on any entry, sorted — the groupable axes. */
export const groupableParameters = (entries: readonly CompareEntry[]): string[] => {
  const names = new Set<string>();
  for (const entry of entries) {
    for (const name of Object.keys(entry.parameters ?? {})) names.add(name);
  }
  return Array.from(names).sort();
};

/**
 * Group label per entry, keyed by `refKey`.
 *
 * `run` reuses the shortest-unique-label pass so the legend matches the tray.
 * A parameter grouping names both the parameter and its value (`seed=42`),
 * because a bare `42` in a legend says nothing; an entry missing that
 * parameter is grouped as such rather than silently folded into another group.
 */
export const groupLabels = (
  entries: readonly CompareEntry[],
  colorBy: ColorBy,
): Map<string, string> => {
  if (colorBy.kind === "run") return shortestUniqueLabels(entries);

  const out = new Map<string, string>();
  for (const entry of entries) {
    out.set(refKey(entry.ref), groupLabelOf(entry, colorBy));
  }
  return out;
};

const groupLabelOf = (entry: CompareEntry, colorBy: ColorBy): string => {
  switch (colorBy.kind) {
    case "experiment":
      return entry.experimentName;
    case "project":
      return entry.projectName;
    case "workspace":
      return entry.workspaceLabel;
    case "parameter": {
      const value = entry.parameters?.[colorBy.name];
      return value === undefined
        ? `${colorBy.name} unset`
        : `${colorBy.name}=${formatParameterValue(value)}`;
    }
    default:
      return entry.runName;
  }
};

const formatParameterValue = (value: unknown): string =>
  typeof value === "object" && value !== null ? JSON.stringify(value) : String(value);
