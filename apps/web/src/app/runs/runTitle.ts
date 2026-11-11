// ─────────────────────────────────────────────────────────────────────────────
// What a run is called on screen (L04 decision 1): the values of the parameters
// that vary across its experiment, with their units — `ase · nve · 2 fs`. The
// run id stays one hover / one copy away. The same title is used by the tab,
// the tree, tables, the breadcrumb and the Preview, so it is computed once,
// where runs are mapped, from parameters alone.
//
// Units: the server declares none, so a recognised unit suffix on the key is
// the unit (`timestep_fs` → `2 fs`). A bare number with no unit keeps its key
// (`seed 42`); a word stands alone (`ase`).
// ─────────────────────────────────────────────────────────────────────────────

import { varyingParameterKeys } from "@/app/renderers/entityWorkbenchData";

/** Key suffix → unit as printed. Case-sensitive: `_K` is kelvin, `_k` is not. */
const UNIT_SUFFIXES: Readonly<Record<string, string>> = {
  fs: "fs",
  ps: "ps",
  ns: "ns",
  us: "µs",
  ms: "ms",
  K: "K",
  eV: "eV",
  meV: "meV",
  kJ: "kJ",
  kcal: "kcal",
  nm: "nm",
  A: "Å",
  ang: "Å",
  bar: "bar",
  atm: "atm",
  GPa: "GPa",
  MPa: "MPa",
};

/** The unit a parameter key declares by its suffix, or null. */
export const parameterUnit = (key: string): string | null => {
  const cut = key.lastIndexOf("_");
  if (cut <= 0) return null;
  return UNIT_SUFFIXES[key.slice(cut + 1)] ?? null;
};

const SEPARATOR = " · ";

/** A number as a person reads it in a title: 2, 0.5, 1e-3, 500 000. */
const formatNumber = (value: number): string => {
  if (Number.isInteger(value)) {
    return Math.abs(value) >= 10_000
      ? value.toLocaleString("en-US").replace(/,/g, " ")
      : String(value);
  }
  const abs = Math.abs(value);
  return abs !== 0 && (abs < 1e-3 || abs >= 1e6)
    ? value.toExponential(2).replace(/\.?0+e/, "e")
    : String(Number(value.toPrecision(4)));
};

/** A parameter value with its unit; the key only where the value alone would be ambiguous. */
export const formatParameter = (key: string, value: unknown): string => {
  if (typeof value === "number") {
    const unit = parameterUnit(key);
    return unit ? `${formatNumber(value)} ${unit}` : `${key} ${formatNumber(value)}`;
  }
  if (typeof value === "boolean") return value ? key : `no ${key}`;
  if (typeof value === "string") return value === "" ? `${key} ""` : value;
  if (value === null || value === undefined) return `${key} —`;
  try {
    return `${key} ${JSON.stringify(value)}`;
  } catch {
    return `${key} ${String(value)}`;
  }
};

/** A parameter value alone, with its unit: what a Params row prints. */
export const formatParameterValue = (key: string, value: unknown): string => {
  if (typeof value === "number") {
    const unit = parameterUnit(key);
    return unit ? `${formatNumber(value)} ${unit}` : formatNumber(value);
  }
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export interface TitledRun {
  id: string;
  name?: string;
  experimentId: string;
  /** Rows from several served workspaces repeat experiment ids. */
  workspaceKey?: string;
  parameters?: Record<string, unknown>;
}

/** The title of a run, given the keys that vary in its experiment. */
export const titleOf = (run: TitledRun, varying: readonly string[]): string => {
  const parameters = run.parameters ?? {};
  const parts = varying
    .filter((key) => key in parameters)
    .map((key) => formatParameter(key, parameters[key]));
  return parts.length > 0 ? parts.join(SEPARATOR) : run.name || run.id;
};

/** Titles for a set of runs, keyed by run id: each experiment's varying keys, in key order. */
export const runTitles = (runs: readonly TitledRun[]): Map<string, string> => {
  const byExperiment = new Map<string, TitledRun[]>();
  for (const run of runs) {
    const group = `${run.workspaceKey ?? ""}\u0000${run.experimentId}`;
    byExperiment.set(group, [...(byExperiment.get(group) ?? []), run]);
  }
  const titles = new Map<string, string>();
  for (const group of byExperiment.values()) {
    const varying = varyingParameterKeys(
      group.map((run) => ({ parameters: run.parameters ?? {} })),
    ).sort((left, right) => left.localeCompare(right));
    for (const run of group) titles.set(run.id, titleOf(run, varying));
  }
  return titles;
};

/** Stamp each run with its title. Returns new objects; the input is not changed. */
export const withRunTitles = <T extends TitledRun>(
  runs: readonly T[],
): (T & { title: string })[] => {
  const titles = runTitles(runs);
  return runs.map((run) => ({ ...run, title: titles.get(run.id) ?? run.name ?? run.id }));
};

/** What to print for a run: its title, else the server's name, else its id. */
export const runLabel = (run: {
  id: string;
  name?: string | null;
  title?: string | null;
}): string => run.title || run.name || run.id;
