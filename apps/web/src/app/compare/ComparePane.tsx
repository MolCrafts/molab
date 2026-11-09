/**
 * Compare (Figma L05-4 … L05-7): an editor tab with views Table · Chart | MolPlot.
 * Table: runs as columns — the first is the baseline until another header is
 * pinned — parameters and results as rows, a value that differs from the
 * baseline in the diff colour, identical parameter rows hidden until asked.
 * Chart: one result across the runs. MolPlot: the runs' metric series (the
 * matrix that reads metric files). A column header's ⋯ sets the baseline,
 * opens the run or removes it from the set.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { ChartLine, GitCompare, MoreHorizontal, Pin, RefreshCw, Table2 } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { CompareBarsChart, EntityPage, StatusIcon } from "@/app/components/entity";
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { usePreview } from "@/app/preview/PreviewContext";
import { chartGroupOf, statusWord } from "@/app/status/vocabulary";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import { CompareTable } from "./CompareTable";
import { type CompareRow, parameterRows, resultRows } from "./compareModel";
import { ExpandIncompleteError, expandToRuns } from "./expandToRuns";
import { MetricDetailDialog } from "./MetricDetailDialog";
import { itemKey, refKey } from "./types";
import { type ComparedRun, useComparedRuns } from "./useComparedRuns";
import { useCompareMetrics } from "./useCompareMetrics";
import { useCompareSet } from "./useCompareSet";

const COLUMN = "w-52 min-w-52 max-w-52";

const ViewLabel = ({ icon: Icon, children }: { icon: typeof Table2; children: string }) => (
  <>
    <Icon aria-hidden className="size-icon-sm" />
    {children}
  </>
);

const Rows = ({
  title,
  rows,
  baseline,
}: {
  title: string;
  rows: readonly CompareRow[];
  baseline: number;
}): JSX.Element => (
  <>
    <tr>
      <th
        colSpan={1 + (rows[0]?.values.length ?? 0)}
        scope="colgroup"
        className="sticky left-0 h-8 bg-background pt-3 text-left text-label font-normal text-muted-foreground"
      >
        {title}
      </th>
    </tr>
    {rows.map((row) => (
      <tr key={row.key} className="h-6 border-b border-border">
        <th
          scope="row"
          className="sticky left-0 z-[1] w-44 min-w-44 truncate bg-background pr-4 text-left font-mono text-label font-normal text-muted-foreground"
        >
          {row.key}
        </th>
        {row.values.map((value, index) => (
          <td
            // biome-ignore lint/suspicious/noArrayIndexKey: one cell per column, columns are stable
            key={index}
            className={cn(
              COLUMN,
              "truncate px-2 font-mono text-label tabular-nums",
              index === baseline && "bg-accent-muted",
              row.differs[index] ? "font-medium text-diff-modified-foreground" : "text-foreground",
            )}
            title={value}
          >
            {value}
          </td>
        ))}
      </tr>
    ))}
  </>
);

const TableView = ({
  runs,
  baseline,
  onBaseline,
  onOpen,
  onRemove,
  canRemove,
}: {
  runs: readonly ComparedRun[];
  baseline: number;
  onBaseline: (index: number) => void;
  onOpen: (run: ComparedRun) => void;
  onRemove: (run: ComparedRun) => void;
  canRemove: (run: ComparedRun) => boolean;
}): JSX.Element => {
  const [showIdentical, setShowIdentical] = useState(false);
  const params = parameterRows(runs, baseline);
  const results = resultRows(runs, baseline);
  const identical = params.filter((row) => row.identical).length;
  const differ = params.length - identical;
  const shown = showIdentical ? params : params.filter((row) => !row.identical);
  return (
    <div className="h-full min-h-0 overflow-auto bg-background px-6 py-4">
      <table aria-label="Compared runs" className="border-collapse text-body">
        <thead>
          <tr className="h-toolbar-compact border-b border-border">
            <th scope="col" className="sticky left-0 z-[1] w-44 min-w-44 bg-background" />
            {runs.map((run, index) => (
              <th
                key={run.key}
                scope="col"
                className={cn(
                  COLUMN,
                  "px-2 text-left font-normal",
                  index === baseline && "bg-accent-muted",
                )}
              >
                <span className="flex min-w-0 items-center gap-1">
                  <StatusIcon
                    status={run.status}
                    label={statusWord(run.status)}
                    className="size-icon-sm shrink-0"
                  />
                  <button
                    type="button"
                    onClick={() => onOpen(run)}
                    title={run.title}
                    className="min-w-0 truncate text-left font-mono text-label text-foreground hover:underline"
                  >
                    {run.title}
                  </button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <WorkbenchIconAction
                        label={`${run.title} actions`}
                        className="ml-auto shrink-0"
                      >
                        <MoreHorizontal aria-hidden className="size-icon-sm" />
                      </WorkbenchIconAction>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-52">
                      <DropdownMenuItem
                        disabled={index === baseline}
                        onSelect={() => onBaseline(index)}
                      >
                        Set as baseline
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => onOpen(run)}>Open run</DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem disabled={!canRemove(run)} onSelect={() => onRemove(run)}>
                        {canRemove(run) ? "Remove from compare" : "Added with its experiment"}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </span>
                <span className="flex items-center gap-1 font-mono text-micro text-muted-foreground">
                  {run.entry.ref.runId}
                  {index === baseline ? (
                    <>
                      <Pin aria-hidden className="size-3" />
                      baseline
                    </>
                  ) : null}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <Rows
            title={`Parameters · ${differ} differ${identical && !showIdentical ? ` · ${identical} identical hidden` : ""}`}
            rows={shown}
            baseline={baseline}
          />
          {identical > 0 ? (
            <tr>
              <td colSpan={1 + runs.length} className="sticky left-0 h-6">
                <button
                  type="button"
                  onClick={() => setShowIdentical((value) => !value)}
                  className="text-label text-accent hover:underline"
                >
                  {showIdentical ? "Hide identical" : `Show ${identical} identical`}
                </button>
              </td>
            </tr>
          ) : null}
          <Rows
            title="Results · from each run's result attempt"
            rows={results}
            baseline={baseline}
          />
        </tbody>
      </table>
    </div>
  );
};

const ChartView = ({
  runs,
  baseline,
  onPreview,
}: {
  runs: readonly ComparedRun[];
  baseline: number;
  onPreview: (run: ComparedRun) => void;
}): JSX.Element => {
  const rows = resultRows(runs, baseline).filter((row) =>
    row.raw.some((value) => typeof value === "number"),
  );
  const [picked, setPicked] = useState<string | null>(null);
  const row = rows.find((candidate) => candidate.key === picked) ?? rows[0];
  if (!row) {
    return (
      <p className="px-6 py-4 text-body text-muted-foreground">No numeric result to chart yet.</p>
    );
  }
  const base = row.raw[baseline];
  return (
    <div className="h-full min-h-0 overflow-auto bg-background px-6 py-4">
      <header className="flex flex-wrap items-center gap-3 pb-3">
        <h2 className="text-body text-foreground">{row.key}</h2>
        <fieldset
          aria-label="Result"
          className="ml-auto flex items-center gap-hairline rounded-hairline bg-muted p-hairline"
        >
          {rows.map((candidate) => (
            <button
              key={candidate.key}
              type="button"
              aria-pressed={candidate.key === row.key}
              onClick={() => setPicked(candidate.key)}
              className={cn(
                "h-6 rounded-hairline px-2 font-mono text-label text-muted-foreground hover:text-foreground",
                candidate.key === row.key && "bg-background text-foreground",
              )}
            >
              {candidate.key}
            </button>
          ))}
        </fieldset>
      </header>
      <div className="max-w-[56rem]">
        <CompareBarsChart
          label={`${row.key} of each compared run`}
          baseline={typeof base === "number" ? base : null}
          bars={runs.map((run, index) => {
            const value = row.raw[index];
            return {
              key: run.key,
              label: `${run.entry.ref.runId}${index === baseline ? " (baseline)" : ""}`,
              value: typeof value === "number" ? value : null,
              printed:
                typeof value === "number"
                  ? (row.values[index] ?? "")
                  : `no result · ${statusWord(run.status).toLowerCase()}`,
              status: chartGroupOf(run.status),
              tip: `${run.title} · ${row.values[index]}`,
            };
          })}
          onPick={(key) => {
            const run = runs.find((candidate) => candidate.key === key);
            if (run) onPreview(run);
          }}
        />
      </div>
    </div>
  );
};

export const ComparePane = ({ snapshot }: NavigationLandingProps): JSX.Element => {
  const set = useCompareSet();
  const preview = usePreview();
  const [view, setView] = useState("table");
  const [baselineKey, setBaselineKey] = useState<string | null>(null);
  const [openMetric, setOpenMetric] = useState<string | null>(null);
  const metrics = useCompareMetrics();

  const expanded = useMemo(() => {
    try {
      return { selected: expandToRuns(set.entries, snapshot), error: null as string | null };
    } catch (error) {
      return {
        selected: [],
        error:
          error instanceof ExpandIncompleteError || error instanceof Error
            ? error.message
            : "Could not expand the selection.",
      };
    }
  }, [set.entries, snapshot]);
  const { runs } = useComparedRuns(expanded.selected);
  const baseline = Math.max(
    0,
    runs.findIndex((run) => run.key === baselineKey),
  );

  // Metric files are read only when the MolPlot view is asked for.
  const scan = metrics.scan;
  useEffect(() => {
    if (view !== "molplot" || expanded.selected.length === 0) return;
    scan(expanded.selected, (entry) => refKey(entry.ref));
  }, [view, expanded.selected, scan]);

  const target = (run: ComparedRun) => ({
    kind: "run" as const,
    runId: run.entry.ref.runId,
    projectId: run.entry.ref.projectId,
    experimentId: run.entry.ref.experimentId,
    workspaceKey: run.entry.ref.workspaceKey,
    label: run.title,
  });
  const runItemKey = (run: ComparedRun): string => itemKey({ kind: "run", ...run.entry.ref });

  if (set.count === 0 || runs.length === 0) {
    return (
      <EntityPage icon={GitCompare} title="Compare">
        <div className="flex flex-1 flex-col items-center justify-center gap-2 bg-background px-6 text-center">
          <GitCompare aria-hidden className="size-10 text-muted-foreground/50" />
          <p className="text-body text-muted-foreground">
            {expanded.error ?? "Nothing to compare"}
          </p>
          <p className="text-label text-muted-foreground">
            Select runs in a Runs table (⌘-click or the checkboxes) and press Compare.
          </p>
        </div>
      </EntityPage>
    );
  }

  return (
    <>
      <EntityPage
        icon={GitCompare}
        title={`Compare · ${runs.length} runs`}
        actions={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <WorkbenchIconAction label="More actions">
                <MoreHorizontal aria-hidden className="size-icon" />
              </WorkbenchIconAction>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem
                disabled={view !== "molplot" || metrics.loading}
                onSelect={() => scan(expanded.selected, (entry) => refKey(entry.ref))}
              >
                <RefreshCw aria-hidden className="size-icon-sm" /> Read metrics again
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={set.clear}
                className="text-destructive focus:text-destructive"
              >
                Clear the compare set
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
        activeTab={view}
        onActiveTabChange={setView}
        tabs={[
          {
            value: "table",
            label: <ViewLabel icon={Table2}>Table</ViewLabel>,
            content: (
              <TableView
                runs={runs}
                baseline={baseline}
                onBaseline={(index) => setBaselineKey(runs[index]?.key ?? null)}
                onOpen={(run) => preview.preview(target(run))}
                onRemove={(run) => set.remove(runItemKey(run))}
                canRemove={(run) => set.keys.has(runItemKey(run))}
              />
            ),
          },
          {
            value: "chart",
            label: <ViewLabel icon={ChartLine}>Chart</ViewLabel>,
            content: (
              <ChartView
                runs={runs}
                baseline={baseline}
                onPreview={(run) => preview.preview(target(run))}
              />
            ),
          },
          {
            value: "molplot",
            dividerBefore: true,
            label: <ViewLabel icon={ChartLine}>MolPlot</ViewLabel>,
            content: (
              <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background">
                <CompareTable
                  entries={expanded.selected}
                  perRunAll={metrics.perRunAll}
                  scanned={metrics.scanned}
                  onOpenMetric={setOpenMetric}
                />
                {metrics.error || metrics.failures.length > 0 ? (
                  <p className="shrink-0 border-t border-border px-6 py-1 text-label text-status-failed-foreground">
                    {[metrics.error, ...metrics.failures].filter(Boolean).join(" · ")}
                  </p>
                ) : null}
              </div>
            ),
          },
        ]}
      />
      <MetricDetailDialog
        metricKey={openMetric}
        entries={expanded.selected}
        perRunAll={metrics.perRunAll}
        onClose={() => setOpenMetric(null)}
      />
    </>
  );
};
