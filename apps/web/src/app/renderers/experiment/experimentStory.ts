// ─────────────────────────────────────────────────────────────────────────────
// What an experiment's Overview says, derived without React (L03): the verdict
// line — the runs' worst latest status, how many of how many, what is still
// going — the one line of evidence naming what the runs that need attention
// share, the outcome of each value of a swept parameter, and the experiment's
// own state words (Planned, Empty) for when nothing has run.
// ─────────────────────────────────────────────────────────────────────────────

import { varyingParameterKeys } from "@/app/renderers/entityWorkbenchData";
import { formatParameterValue } from "@/app/runs/runTitle";
import {
  countStatuses,
  isActiveStatus,
  normalizeStatus,
  type StatusCounts,
  type StatusKey,
} from "@/app/status/vocabulary";

/** What the story needs of a run. */
export interface StoryRun {
  id: string;
  status: string;
  parameters?: Record<string, unknown>;
  errorMessage?: string | null;
}

export type ExperimentState =
  | "attention"
  | "active"
  | "succeeded"
  | "planned"
  | "empty"
  | "settled";

export interface ExperimentVerdict {
  state: ExperimentState;
  /** The glyph and colour: a status key, or `pending` for Planned / Empty. */
  status: StatusKey;
  /** The word: a status word, or Planned / Empty. */
  word: string;
  /** "1 failed · 1 interrupted of 12 runs". */
  subject: string;
  /** Right edge: "2 active", "8 done". */
  aside: string | null;
  /** Level 3. */
  evidence: string | null;
  /** The statuses the subject stands for, as a Runs filter (`status:failed,interrupted`). */
  subjectFilter: string | null;
  /** The statuses `aside` stands for. */
  asideFilter: string | null;
  /** Runs whose latest attempt failed or was interrupted: what Resume n resumes. */
  attention: string[];
}

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? "" : "s"}`;

export const firstLine = (text: string | null | undefined): string | null =>
  text
    ?.split("\n")
    .find((line) => line.trim())
    ?.trim() ?? null;

/** The parameter values every listed run shares that the experiment's other runs do not all share. */
export const sharedValues = (picked: readonly StoryRun[], all: readonly StoryRun[]): string[] => {
  if (picked.length < 1 || picked.length === all.length) return [];
  const keys = varyingParameterKeys(all.map((run) => ({ parameters: run.parameters ?? {} })));
  return keys.flatMap((key) => {
    const values = new Set(picked.map((run) => JSON.stringify(run.parameters?.[key])));
    if (values.size !== 1) return [];
    const value = picked[0]?.parameters?.[key];
    return value === undefined ? [] : [`${key} = ${formatParameterValue(key, value)}`];
  });
};

/** "Both", "All 3", or nothing for one run. */
export const quantifier = (count: number): string => (count === 2 ? "Both" : `All ${count}`);

/** The worst latest status of an experiment's runs, in one line, and what the runs needing it share. */
export const experimentVerdict = (
  runs: readonly StoryRun[],
  { declaredCells = 0 }: { declaredCells?: number } = {},
): ExperimentVerdict => {
  const statuses = runs.map((run) => normalizeStatus(run.status));
  const counts = countStatuses(statuses);
  const total = runs.length;
  const of = `of ${plural(total, "run")}`;
  const active = statuses.filter((status) => isActiveStatus(status)).length;
  const attentionRuns = runs.filter((_run, index) =>
    ["failed", "interrupted"].includes(statuses[index] ?? ""),
  );
  const base = {
    subjectFilter: null,
    asideFilter: null,
    attention: attentionRuns.map((run) => run.id),
  };

  if (total === 0) {
    return declaredCells > 0
      ? {
          ...base,
          state: "planned",
          status: "pending",
          word: "Planned",
          subject: `${plural(declaredCells, "run")} declared`,
          aside: null,
          evidence: "The parameter space is declared; nothing has run yet.",
        }
      : {
          ...base,
          state: "empty",
          status: "pending",
          word: "Empty",
          subject: "No runs yet",
          aside: null,
          evidence: null,
        };
  }

  if (attentionRuns.length > 0) {
    const failed = counts.failed;
    const interrupted = counts.interrupted;
    const parts = [
      failed ? `${failed} failed` : null,
      interrupted ? `${interrupted} interrupted` : null,
    ]
      .filter(Boolean)
      .join(" · ");
    const shared = sharedValues(attentionRuns, runs);
    const errors = [
      ...new Set(attentionRuns.map((run) => firstLine(run.errorMessage)).filter(Boolean)),
    ].slice(0, 2) as string[];
    const where =
      shared.length > 0
        ? attentionRuns.length > 1
          ? `${quantifier(attentionRuns.length)} at ${shared.join(", ")}`
          : `At ${shared.join(", ")}`
        : null;
    return {
      ...base,
      state: "attention",
      status: failed ? "failed" : "interrupted",
      word: failed ? "Failed" : "Interrupted",
      subject: `${parts} ${of}`,
      aside: active ? `${active} active` : null,
      evidence: [where, ...errors].filter(Boolean).join(" · ") || null,
      subjectFilter: "status:failed,interrupted",
      asideFilter: active ? "status:running,queued" : null,
    };
  }

  if (active > 0) {
    const running = statuses.filter(
      (status) => status === "running" || status === "finalizing",
    ).length;
    const queued = statuses.filter((status) => status === "queued").length;
    const parts = [running ? `${running} running` : null, queued ? `${queued} queued` : null]
      .filter(Boolean)
      .join(" · ");
    const done = counts.succeeded;
    return {
      ...base,
      state: "active",
      status: running ? "running" : "queued",
      word: running ? "Running" : "Queued",
      subject: `${parts} ${of}`,
      aside: done ? `${done} done` : null,
      evidence: null,
      subjectFilter: "status:running,queued",
      asideFilter: done ? "status:succeeded" : null,
    };
  }

  const notStarted = statuses.filter((status) => status === "pending").length;
  if (counts.succeeded === total) {
    return {
      ...base,
      state: "succeeded",
      status: "succeeded",
      word: "Succeeded",
      subject: total === 1 ? "the run" : `all ${plural(total, "run")}`,
      aside: null,
      evidence: null,
    };
  }
  if (notStarted === total) {
    return {
      ...base,
      state: "planned",
      status: "pending",
      word: "Planned",
      subject: `${plural(total, "run")} not started`,
      aside: null,
      evidence: null,
      subjectFilter: "status:pending",
    };
  }
  const rest = [
    counts.cancelled ? `${counts.cancelled} cancelled` : null,
    notStarted ? `${notStarted} not started` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return {
    ...base,
    state: "settled",
    status: counts.succeeded > 0 ? "succeeded" : "cancelled",
    word: counts.succeeded > 0 ? "Succeeded" : "Cancelled",
    subject: `${counts.succeeded} ${of}`,
    aside: rest || null,
    evidence: null,
    subjectFilter: "status:succeeded",
    asideFilter: rest ? "status:cancelled,pending" : null,
  };
};

export interface OutcomeGroup {
  id: string;
  label: string;
  counts: StatusCounts;
}

const compareValues = (left: unknown, right: unknown): number =>
  typeof left === "number" && typeof right === "number"
    ? left - right
    : String(left).localeCompare(String(right));

/** The latest status of each run, by the values of one parameter (unset filed last). */
export const outcomeByParameter = (runs: readonly StoryRun[], key: string): OutcomeGroup[] => {
  const groups = new Map<string, { value: unknown; statuses: string[] }>();
  for (const run of runs) {
    const set = run.parameters !== undefined && key in run.parameters;
    const value = set ? run.parameters?.[key] : undefined;
    const id = set ? JSON.stringify(value) : "\u0000unset";
    const group = groups.get(id) ?? { value, statuses: [] };
    groups.set(id, { ...group, statuses: [...group.statuses, run.status] });
  }
  return [...groups.entries()]
    .sort(([leftId, left], [rightId, right]) =>
      leftId === "\u0000unset"
        ? 1
        : rightId === "\u0000unset"
          ? -1
          : compareValues(left.value, right.value),
    )
    .map(([id, group]) => ({
      id,
      label: id === "\u0000unset" ? `${key} unset` : formatParameterValue(key, group.value),
      counts: countStatuses(group.statuses),
    }));
};

/** How many runs a declared parameter space asks for: the product of its list lengths. */
export const declaredCellCount = (space: Record<string, unknown> | undefined): number => {
  const lists = Object.values(space ?? {}).filter(
    (value): value is unknown[] => Array.isArray(value) && value.length > 0,
  );
  return lists.length === 0 ? 0 : lists.reduce((count, list) => count * list.length, 1);
};

/** Each combination a declared parameter space asks for (lists only; at most `limit`). */
export const declaredCells = (
  space: Record<string, unknown> | undefined,
  limit = 2000,
): Record<string, unknown>[] => {
  const axes = Object.entries(space ?? {}).filter(
    (entry): entry is [string, unknown[]] => Array.isArray(entry[1]) && entry[1].length > 0,
  );
  if (axes.length === 0) return [];
  let cells: Record<string, unknown>[] = [{}];
  for (const [key, values] of axes) {
    cells = cells.flatMap((cell) => values.map((value) => ({ ...cell, [key]: value })));
    if (cells.length > limit) return cells.slice(0, limit);
  }
  return cells;
};

/** How many declared combinations have no run with those values yet. */
export const missingCellCount = (
  space: Record<string, unknown> | undefined,
  runs: readonly Pick<StoryRun, "parameters">[],
): number => {
  const cells = declaredCells(space);
  const sameValue = (left: unknown, right: unknown): boolean =>
    JSON.stringify(left) === JSON.stringify(right) || String(left) === String(right);
  return cells.filter(
    (cell) =>
      !runs.some((run) =>
        Object.entries(cell).every(([key, value]) => sameValue(run.parameters?.[key], value)),
      ),
  ).length;
};
