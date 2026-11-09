/**
 * The Dashboard side bar is the triage list (Figma L01-1, L01-3, decision 2):
 * Needs attention (latest attempt failed or interrupted), Active (running,
 * then queued) and Finished · 24h (folded). One 28px row per run — its title
 * and its experiment. A click previews the run (L12); ↵ or a double click
 * opens it. These lists replace the Dashboard's old Attention and Timeline
 * views and its project list (the Projects section has the projects).
 */

import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { type JSX, type ReactNode, useMemo, useState } from "react";
import { StatusIcon } from "@/app/components/entity";
import { dashboardLists } from "@/app/dashboard/dashboardLists";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import { runPresentationStatus } from "@/app/runs/projections";
import { runLabel } from "@/app/runs/runTitle";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";

/** Rows a list shows before “n more” opens the rest in Runs. */
export const LIST_LIMIT = 12;

const targetOf = (run: WorkspaceRunRow): PreviewTarget => ({
  kind: "run",
  runId: run.id,
  projectId: run.projectId,
  experimentId: run.experimentId,
  workspaceKey: run.workspaceKey,
  label: runLabel(run),
});

const Section = ({
  title,
  count,
  defaultOpen = true,
  children,
}: {
  title: string;
  count: number;
  defaultOpen?: boolean;
  children: ReactNode;
}): JSX.Element => {
  const [open, setOpen] = useState(defaultOpen);
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <section aria-label={title}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-shell-crumbs w-full items-center gap-1 px-1 text-micro font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
      >
        <Chevron aria-hidden className="size-icon-sm" />
        <span className="flex-1 text-left">{title}</span>
        {count > 0 ? (
          <span className="min-w-4 rounded-full bg-muted px-1 text-center tabular-nums">
            {count}
          </span>
        ) : null}
      </button>
      {open ? children : null}
    </section>
  );
};

/** One list of runs, 28px rows; shared with the phone Overview (L01-8). */
export const RunList = ({
  runs,
  more,
  empty,
}: {
  runs: readonly WorkspaceRunRow[];
  more: string;
  empty: string;
}): JSX.Element => {
  const preview = usePreview();
  if (runs.length === 0) {
    return <p className="px-6 py-1 text-label text-muted-foreground">{empty}</p>;
  }
  const shown = runs.slice(0, LIST_LIMIT);
  return (
    <ul>
      {shown.map((run) => {
        const target = targetOf(run);
        const selected = preview.isPreviewed(target);
        return (
          <li key={`${run.workspaceKey}:${run.id}`}>
            <button
              type="button"
              aria-label={`${runLabel(run)} · ${run.experimentName}`}
              aria-current={selected ? "true" : undefined}
              className={`flex h-7 w-full min-w-0 items-center gap-2 pr-3 pl-6 text-left hover:bg-interactive focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring ${selected ? "bg-accent-muted" : ""}`}
              onClick={(event) =>
                event.metaKey || event.ctrlKey
                  ? preview.open(target, { background: true })
                  : preview.preview(target)
              }
              onDoubleClick={() => preview.open(target)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  preview.open(target);
                }
              }}
            >
              <StatusIcon status={runPresentationStatus(run)} className="size-icon-sm shrink-0" />
              <span className="max-w-[55%] shrink-0 truncate font-mono text-label text-foreground">
                {runLabel(run)}
              </span>
              <span className="min-w-0 truncate text-label text-muted-foreground">
                {run.experimentName}
              </span>
            </button>
          </li>
        );
      })}
      {runs.length > shown.length ? (
        <li className="px-6 py-1 text-label text-muted-foreground">
          +{runs.length - shown.length} {more}
        </li>
      ) : null}
    </ul>
  );
};

export const DashboardExplorer = ({ onRefresh }: NavigationExplorerProps): JSX.Element => {
  const { rows, refresh, loading } = useWorkspaceRuns();
  const lists = useMemo(() => dashboardLists(rows), [rows]);

  const actions = (
    <WorkbenchIconAction
      label="Sync now"
      disabled={loading}
      onClick={() => {
        refresh();
        onRefresh();
      }}
    >
      <RefreshCw className="size-3.5" />
    </WorkbenchIconAction>
  );

  return (
    <LeftExplorer title="Dashboard" actions={actions} bodyClassName="py-1">
      <Section title="Needs attention" count={lists.attention.length}>
        <RunList runs={lists.attention} more="more in Runs" empty="Nothing needs you." />
      </Section>
      <Section title="Active" count={lists.active.length}>
        <RunList runs={lists.active} more="more in Runs" empty="Nothing is running." />
      </Section>
      <Section title="Finished · 24h" count={lists.finished.length} defaultOpen={false}>
        <RunList runs={lists.finished} more="more in Runs" empty="Nothing finished today." />
      </Section>
    </LeftExplorer>
  );
};
