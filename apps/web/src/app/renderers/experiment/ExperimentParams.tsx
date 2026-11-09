/**
 * Experiment Params (Figma L03-6): the parameter space. Each swept key with
 * its kind and unit; each value with how many runs used it and their outcome
 * glyphs; a declared value no run has used yet, dashed. Fixed values below.
 * When declared combinations are missing, “Sweep the n not run…” offers them.
 */

import type { JSX } from "react";
import { StatusIcon } from "@/app/components/entity";
import { missingCellCount } from "@/app/renderers/experiment/experimentStory";
import { formatParameterValue, parameterUnit } from "@/app/runs/runTitle";
import { statusWord } from "@/app/status/vocabulary";
import type { ExperimentSummary, RunSummary } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";

/** Glyphs drawn per value before the rest are counted. */
const MAX_GLYPHS = 12;

interface ValueCell {
  key: string;
  value: unknown;
  runs: RunSummary[];
}

const sameValue = (left: unknown, right: unknown): boolean =>
  JSON.stringify(left) === JSON.stringify(right) || String(left) === String(right);

const compareValues = (left: unknown, right: unknown): number =>
  typeof left === "number" && typeof right === "number"
    ? left - right
    : String(left).localeCompare(String(right), undefined, { numeric: true });

const kindOf = (key: string, values: readonly unknown[]): string => {
  if (values.every((value) => typeof value === "number")) {
    const unit = parameterUnit(key);
    return unit ? `number · ${unit}` : "number";
  }
  if (values.every((value) => typeof value === "boolean")) return "boolean";
  return values.every((value) => typeof value === "string") ? "word" : "value";
};

/** Every key: the values runs used plus the ones the space declares. */
const parameterCells = (
  space: Record<string, unknown>,
  runs: readonly RunSummary[],
): { key: string; cells: ValueCell[] }[] => {
  const keys = [
    ...new Set([
      ...Object.keys(space),
      ...runs.flatMap((run) => Object.keys(run.parameters ?? {})),
    ]),
  ].sort();
  return keys.map((key) => {
    const declared = Array.isArray(space[key]) ? (space[key] as unknown[]) : [];
    const values: unknown[] = [];
    for (const value of [
      ...declared,
      ...runs.flatMap((run) =>
        run.parameters && key in run.parameters ? [run.parameters[key]] : [],
      ),
    ]) {
      if (!values.some((seen) => sameValue(seen, value))) values.push(value);
    }
    return {
      key,
      cells: values.sort(compareValues).map((value) => ({
        key,
        value,
        runs: runs.filter(
          (run) => run.parameters && key in run.parameters && sameValue(run.parameters[key], value),
        ),
      })),
    };
  });
};

const Cell = ({ cell }: { cell: ValueCell }): JSX.Element => {
  const label = formatParameterValue(cell.key, cell.value);
  if (cell.runs.length === 0) {
    return (
      <span
        title={`${cell.key} = ${label}: declared, not run yet`}
        className="inline-flex h-6 items-center gap-2 rounded-hairline border border-dashed border-border px-2 text-muted-foreground"
      >
        <span className="font-mono">{label}</span>
        <span className="text-label">not run</span>
      </span>
    );
  }
  const shown = cell.runs.slice(0, MAX_GLYPHS);
  return (
    <span
      title={`${cell.key} = ${label}: ${cell.runs.length} runs`}
      className="inline-flex h-6 items-center gap-2 rounded-hairline bg-muted px-2"
    >
      <span className="font-mono text-foreground">{label}</span>
      <span className="text-label tabular-nums text-muted-foreground">{cell.runs.length}</span>
      <span className="inline-flex items-center gap-hairline">
        {shown.map((run) => (
          <StatusIcon
            key={run.id}
            status={run.status}
            label={statusWord(run.status)}
            className="size-3"
          />
        ))}
        {cell.runs.length > shown.length ? (
          <span className="text-micro text-muted-foreground">
            +{cell.runs.length - shown.length}
          </span>
        ) : null}
      </span>
    </span>
  );
};

export const ExperimentParams = ({
  experiment,
  runs,
  onSweep,
}: {
  experiment: ExperimentSummary;
  runs: readonly RunSummary[];
  onSweep: () => void;
}): JSX.Element => {
  const space = experiment.parameterSpace ?? {};
  const keys = parameterCells(space, runs);
  const swept = keys.filter((entry) => entry.cells.length > 1);
  const fixed = keys.filter((entry) => entry.cells.length === 1);
  const missing = missingCellCount(space, runs);
  const notRunValues = swept.reduce(
    (count, entry) => count + entry.cells.filter((cell) => cell.runs.length === 0).length,
    0,
  );
  const combinations = new Set(
    runs.map((run) => JSON.stringify(swept.map((entry) => run.parameters?.[entry.key]))),
  ).size;

  if (keys.length === 0) {
    return (
      <div className="h-full bg-background px-6 py-6 text-body text-muted-foreground">
        No parameters declared and no run has taken any.
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-auto bg-background">
      <div className="max-w-[72rem] space-y-8 px-6 py-6">
        {swept.length > 0 ? (
          <section aria-label="Swept parameters">
            <header className="flex items-baseline gap-3 pb-1">
              <h2 className="text-body text-foreground">Swept</h2>
              <span className="ml-auto text-label text-muted-foreground">
                {swept.length} {swept.length === 1 ? "parameter" : "parameters"} · {combinations}{" "}
                {combinations === 1 ? "combination" : "combinations"} run
                {notRunValues > 0
                  ? ` · ${notRunValues} declared ${notRunValues === 1 ? "value" : "values"} not run`
                  : ""}
              </span>
            </header>
            <dl className="divide-y divide-border border-y border-border">
              {swept.map((entry) => (
                <div
                  key={entry.key}
                  className="grid grid-cols-[12rem_7rem_minmax(0,1fr)] items-center gap-x-4 py-1"
                >
                  <dt className="truncate font-mono text-label text-foreground">{entry.key}</dt>
                  <dd className="text-label text-muted-foreground">
                    {kindOf(
                      entry.key,
                      entry.cells.map((cell) => cell.value),
                    )}
                  </dd>
                  <dd className="flex flex-wrap gap-2 text-label">
                    {entry.cells.map((cell) => (
                      <Cell key={JSON.stringify(cell.value)} cell={cell} />
                    ))}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        {fixed.length > 0 ? (
          <section aria-label="Fixed parameters">
            <h2 className="pb-1 text-body text-foreground">Fixed for the experiment</h2>
            <dl className="divide-y divide-border border-y border-border">
              {fixed.map((entry) => (
                <div
                  key={entry.key}
                  className="grid h-7 grid-cols-[12rem_minmax(0,1fr)] items-center gap-x-4"
                >
                  <dt className="truncate font-mono text-label text-foreground">{entry.key}</dt>
                  <dd className="truncate font-mono text-label text-foreground">
                    {formatParameterValue(entry.key, entry.cells[0]?.value)}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        {missing > 0 ? (
          <div className="flex items-center gap-3">
            <DialogButton kind="secondary" onClick={onSweep}>
              Sweep the {missing} not run…
            </DialogButton>
            <span className="text-label text-muted-foreground">
              declared combinations with no run yet
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
};
