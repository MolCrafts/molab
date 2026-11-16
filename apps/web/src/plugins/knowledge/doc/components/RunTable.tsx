/**
 * `<molab-run-table experiment=… columns=… where=… limit=…>` (L10): a live
 * query of one experiment's runs — status glyph, run label, then one column
 * per name: the run's parameter, else its scalar result. A row click previews
 * the run, a double-click opens it.
 */

import { RefreshCw, Table2 } from "lucide-react";
import { type JSX, type KeyboardEvent, useMemo } from "react";
import { StatusIcon } from "@/app/components/entity";
import { usePreview } from "@/app/preview/PreviewContext";
import { varyingParameterKeys } from "@/app/renderers/entityWorkbenchData";
import { runLabel } from "@/app/runs/runTitle";
import type { RunSummary } from "@/app/types";
import { cn } from "@/lib/utils";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentNotice } from "../frame";
import { runPreviewTarget, useDocExperiment, useRunResults } from "./docRuns";
import {
  formatCell,
  formatWhere,
  matchesWhere,
  parseColumns,
  parseLimit,
  parseWhere,
  runValue,
  type WhereCondition,
} from "./runQuery";

const NAME = "molab-run-table";

const NO_RUNS: readonly RunSummary[] = [];

type Results = ReturnType<typeof useRunResults>["byRun"];

/** A column read from a result, not a parameter, needs the outputs query. */
const needsResults = (keys: readonly string[], runs: readonly RunSummary[]): boolean =>
  keys.some((key) => !runs.some((run) => key in (run.parameters ?? {})));

const selectRuns = (
  runs: readonly RunSummary[],
  conditions: readonly WhereCondition[],
  results: Results,
  limit: number | null,
): RunSummary[] => {
  const kept = runs.filter((run) =>
    matchesWhere(conditions, (key) => runValue(run.parameters ?? {}, results.get(run.id), key)),
  );
  return limit === null ? kept : kept.slice(0, limit);
};

const Row = ({
  run,
  columns,
  numeric,
  results,
}: {
  run: RunSummary;
  columns: readonly string[];
  numeric: ReadonlySet<string>;
  results: Results;
}): JSX.Element => {
  const preview = usePreview();
  const target = runPreviewTarget(run);
  const onKeyDown = (event: KeyboardEvent): void => {
    if (event.key === "Enter") preview.open(target);
    if (event.key === " ") {
      event.preventDefault();
      preview.preview(target);
    }
  };
  return (
    <tr
      tabIndex={0}
      title={run.id}
      onClick={() => preview.preview(target)}
      onDoubleClick={() => preview.open(target)}
      onKeyDown={onKeyDown}
      className="h-shell-button cursor-pointer border-t border-border hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
    >
      <td className="px-3">
        <span className="flex min-w-0 items-center gap-2">
          <StatusIcon status={run.status} />
          <span className="truncate font-mono">{runLabel(run)}</span>
        </span>
      </td>
      {columns.map((column) => {
        const cell = formatCell(runValue(run.parameters ?? {}, results.get(run.id), column));
        return (
          <td
            key={column}
            className={cn(
              "px-3 whitespace-nowrap",
              numeric.has(column) ? "text-right tabular-nums" : "text-left",
              cell.text === "—" && "text-muted-foreground",
            )}
          >
            {cell.text}
          </td>
        );
      })}
    </tr>
  );
};

const Footer = ({ name, where }: { name: string; where: string }): JSX.Element => (
  <>
    <RefreshCw aria-hidden className="size-icon-sm flex-none" />
    <span className="truncate">{["live", name, where].filter(Boolean).join(" · ")}</span>
  </>
);

export const RunTable = ({ attrs }: DocComponentProps): JSX.Element => {
  const found = useDocExperiment(attrs.experiment);
  const runs = found?.runs ?? NO_RUNS;
  const where = useMemo(() => parseWhere(attrs.where), [attrs.where]);
  const columns = useMemo(() => {
    const written = parseColumns(attrs.columns);
    return written.length > 0 ? written : varyingParameterKeys(runs).sort();
  }, [attrs.columns, runs]);
  const wanted = useMemo(
    () => [...columns, ...where.conditions.map((condition) => condition.key)],
    [columns, where.conditions],
  );
  const { byRun } = useRunResults(found?.experiment.id ?? null, needsResults(wanted, runs));
  const rows = useMemo(
    () => selectRuns(runs, where.conditions, byRun, parseLimit(attrs.limit)),
    [runs, where.conditions, byRun, attrs.limit],
  );
  const numeric = useMemo(
    () =>
      new Set(
        columns.filter((column) =>
          rows.some(
            (run) => formatCell(runValue(run.parameters ?? {}, byRun.get(run.id), column)).numeric,
          ),
        ),
      ),
    [columns, rows, byRun],
  );

  if (!attrs.experiment) {
    return (
      <ComponentNotice name={NAME}>
        Needs an experiment=molab:experiment/… attribute.
      </ComponentNotice>
    );
  }
  if (!found) {
    return <ComponentNotice name={NAME}>{attrs.experiment} does not resolve.</ComponentNotice>;
  }
  if (where.invalid.length > 0) {
    return (
      <ComponentNotice name={NAME}>Cannot read where: {where.invalid.join(", ")}</ComponentNotice>
    );
  }
  return (
    <ComponentFrame
      label={`Runs of ${found.experiment.name}`}
      footer={<Footer name={found.experiment.name} where={formatWhere(where.conditions)} />}
    >
      <table className="w-full border-collapse">
        <thead>
          <tr className="h-control-compact text-label text-muted-foreground">
            <th scope="col" className="px-3 text-left font-normal">
              run
            </th>
            {columns.map((column) => (
              <th
                key={column}
                scope="col"
                className={cn(
                  "px-3 font-normal whitespace-nowrap",
                  numeric.has(column) ? "text-right" : "text-left",
                )}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr className="h-shell-button border-t border-border">
              <td colSpan={columns.length + 1} className="px-3 text-muted-foreground">
                {runs.length === 0 ? "No runs yet." : "No run matches."}
              </td>
            </tr>
          ) : (
            rows.map((run) => (
              <Row key={run.id} run={run} columns={columns} numeric={numeric} results={byRun} />
            ))
          )}
        </tbody>
      </table>
    </ComponentFrame>
  );
};

export const runTableSpec: DocComponentSpec = {
  name: NAME,
  label: "Run table",
  description: "A live query of an experiment's runs: status, parameters, results",
  keywords: ["runs", "table", "query", "results", "parameters", "where"],
  icon: Table2,
  template: { experiment: "molab:experiment/", columns: "" },
  Component: RunTable,
};
