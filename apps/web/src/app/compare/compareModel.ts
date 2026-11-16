// ─────────────────────────────────────────────────────────────────────────────
// The Compare table (L05-4, L05-6) without React: runs as columns, parameters
// and results as rows, each value against the baseline column. A parameter row
// where every run agrees is “identical” and hidden until asked for.
// ─────────────────────────────────────────────────────────────────────────────

import { formatSpan } from "@/app/components/entity";
import { formatFigure } from "@/app/renderers/run/runStory";
import { formatParameterValue } from "@/app/runs/runTitle";

export interface ComparedColumn {
  key: string;
  parameters: Record<string, unknown>;
  /** Scalar results of the run's result attempt; null while loading or when there is none. */
  results: Record<string, unknown> | null;
  /** Wall time of the result attempt (else the latest), seconds. */
  seconds: number | null;
}

export interface CompareRow {
  key: string;
  /** Printed values, one per column (`—` when the run has none). */
  values: string[];
  /** Raw values, for charts and sorting. */
  raw: unknown[];
  /** Per column: the value differs from the baseline column's. */
  differs: boolean[];
  /** Every column agrees. */
  identical: boolean;
}

export const MISSING = "—";

const same = (left: unknown, right: unknown): boolean =>
  JSON.stringify(left) === JSON.stringify(right);

const rowOf = (
  key: string,
  raw: unknown[],
  format: (value: unknown) => string,
  baseline: number,
): CompareRow => {
  const values = raw.map((value) =>
    value === undefined || value === null ? MISSING : format(value),
  );
  const base = raw[baseline];
  return {
    key,
    values,
    raw,
    differs: raw.map(
      (value, index) =>
        index !== baseline && value !== undefined && value !== null && !same(value, base),
    ),
    identical: raw.every((value) => same(value, raw[0])),
  };
};

/** Parameter rows: varying keys first, then the ones every run shares, each by name. */
export const parameterRows = (columns: readonly ComparedColumn[], baseline = 0): CompareRow[] => {
  const keys = [...new Set(columns.flatMap((column) => Object.keys(column.parameters)))];
  return keys
    .map((key) =>
      rowOf(
        key,
        columns.map((column) => column.parameters[key]),
        (value) => formatParameterValue(key, value),
        baseline,
      ),
    )
    .sort(
      (left, right) =>
        Number(left.identical) - Number(right.identical) || left.key.localeCompare(right.key),
    );
};

/** Result rows: every scalar result any run reported (numbers first), then time. */
export const resultRows = (columns: readonly ComparedColumn[], baseline = 0): CompareRow[] => {
  const keys: string[] = [];
  for (const column of columns) {
    for (const [key, value] of Object.entries(column.results ?? {})) {
      if (["number", "string", "boolean"].includes(typeof value) && !keys.includes(key))
        keys.push(key);
    }
  }
  const numeric = (key: string): boolean =>
    columns.some((column) => typeof column.results?.[key] === "number");
  const ordered = [...keys].sort((left, right) => Number(numeric(right)) - Number(numeric(left)));
  return [
    ...ordered.map((key) =>
      rowOf(
        key,
        columns.map((column) => column.results?.[key]),
        (value) => (typeof value === "number" ? formatFigure(value) : String(value)),
        baseline,
      ),
    ),
    rowOf(
      "time",
      columns.map((column) => (column.seconds === null ? null : Math.round(column.seconds))),
      (value) => formatSpan(value as number),
      baseline,
    ),
  ];
};
