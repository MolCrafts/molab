/**
 * The workspace Overview (Figma L01-1, L01-2, L01-4, L01-6, L01-7): the L02
 * project Overview one level up. A verdict over every run of the workspace —
 * whose counts open Runs filtered to them — and one line naming the projects
 * the runs needing attention sit in; the three gauges; Activity (started above,
 * finished below); then Outcome by project, Backends and Duration by project.
 * Dragging over Activity, or picking a backend, narrows the whole page; a strip
 * says so and clears it. Lists of runs live in the side bar, not here.
 */

import { Funnel, X } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import { GaugeSection, MixChart, StatusGlyphLegend, StatusIcon } from "@/app/components/entity";
import { RunList } from "@/app/dashboard/DashboardExplorer";
import { dashboardLists } from "@/app/dashboard/dashboardLists";
import {
  ActivityPanel,
  backendGroups,
  DurationsBy,
  EmptyLine,
} from "@/app/dashboard/dashboardWidgets";
import {
  applyOverviewFilter,
  isFiltered,
  NO_FILTER,
  type OverviewFilter,
} from "@/app/dashboard/overviewFilter";
import { Gauges, Verdict } from "@/app/renderers/experiment/ExperimentOverview";
import {
  type NamedGroup,
  outcomeByGroup,
  PROJECTS,
  scopeRunsOf,
  scopeVerdict,
} from "@/app/renderers/scopeStory";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction } from "@/components/workbench";

const RUN_WORDING = { unit: ["run", "runs"] } as const;
const ATTEMPT_WORDING = { unit: ["attempt", "attempts"] } as const;

export interface WorkspaceOverviewProps {
  rows: readonly WorkspaceRunRow[];
  projects: readonly NamedGroup[];
  /** Runs the snapshot already holds, for their first error line. */
  known: readonly { id: string; errorMessage?: string | null }[];
  /** The inventory is a truncated page, or part of it failed to load. */
  partial: boolean;
  inventoryBlocked: boolean;
  onOpenRuns: (filter?: string) => void;
  onPreviewProject: (projectId: string) => void;
  onNewProject: () => void;
}

const pad2 = (value: number): string => value.toString().padStart(2, "0");
const clock = (ms: number): string => {
  const date = new Date(ms);
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
};

/** “Showing 9 of 21 runs · ran 15:00–18:00 · on molq ✕”: a run counts when an attempt was alive in the window. */
const FilterStrip = ({
  filter,
  shown,
  total,
  onClear,
}: {
  filter: OverviewFilter;
  shown: number;
  total: number;
  onClear: () => void;
}): JSX.Element => (
  <div
    role="status"
    aria-label="Overview filter"
    className="flex h-7 min-w-0 shrink-0 items-center gap-2 border-b border-border bg-accent-muted px-6 text-label text-foreground"
  >
    <Funnel aria-hidden className="size-icon-sm text-muted-foreground" />
    <span className="min-w-0 truncate">
      Showing <b className="tabular-nums">{shown}</b> of {total} runs
      {filter.window ? ` · ran ${clock(filter.window[0])}–${clock(filter.window[1])}` : ""}
      {filter.backend ? ` · on ${filter.backend}` : ""}
    </span>
    <WorkbenchIconAction label="Clear filter" className="ml-auto" onClick={onClear}>
      <X aria-hidden />
    </WorkbenchIconAction>
  </div>
);

/** Nothing has run: what is there, in order, with the one action each needs. */
const FirstSteps = ({
  projects,
  onNewProject,
  onOpenRuns,
}: {
  projects: readonly NamedGroup[];
  onNewProject: () => void;
  onOpenRuns: () => void;
}): JSX.Element => (
  <ol
    aria-label="What this workspace needs"
    className="max-w-[40rem] divide-y divide-border border-b border-border"
  >
    <li className="flex min-h-11 items-center gap-3 py-1">
      <StatusIcon
        status={projects.length > 0 ? "succeeded" : "pending"}
        className="size-icon shrink-0"
      />
      <span className="min-w-0 flex-1">
        <span className="block text-body text-foreground">Projects</span>
        <span className="block truncate text-label text-muted-foreground">
          {projects.length > 0
            ? projects.map((project) => project.name).join(" · ")
            : "None yet · a project holds experiments, an experiment holds runs"}
        </span>
      </span>
      <DialogButton kind="secondary" onClick={onNewProject}>
        New project…
      </DialogButton>
    </li>
    <li className="flex min-h-11 items-center gap-3 py-1">
      <StatusIcon status="pending" className="size-icon shrink-0" />
      <span className="min-w-0 flex-1">
        <span className="block text-body text-foreground">Runs</span>
        <span className="block truncate text-label text-muted-foreground">
          None yet · start one from an experiment, or adopt a job that ran outside molab
        </span>
      </span>
      <DialogButton kind="secondary" onClick={onOpenRuns}>
        Open runs
      </DialogButton>
    </li>
  </ol>
);

export const WorkspaceOverview = ({
  rows,
  projects,
  known,
  partial,
  inventoryBlocked,
  onOpenRuns,
  onPreviewProject,
  onNewProject,
}: WorkspaceOverviewProps): JSX.Element => {
  const [filter, setFilter] = useState<OverviewFilter>(NO_FILTER);
  // Activity keeps its whole window as context for the brush; the backend pick narrows it.
  const byBackend = useMemo(
    () => applyOverviewFilter(rows, { window: null, backend: filter.backend }),
    [rows, filter.backend],
  );
  const scoped = useMemo(() => applyOverviewFilter(rows, filter), [rows, filter]);
  // Backends are counted before the backend pick, so the picked bar stays among its peers.
  const backends = useMemo(
    () => backendGroups(applyOverviewFilter(rows, { window: filter.window, backend: null })),
    [rows, filter.window],
  );
  const runs = useMemo(() => scopeRunsOf(scoped, known, "project"), [scoped, known]);
  const verdict = useMemo(() => {
    const told = scopeVerdict(runs, projects, PROJECTS);
    return partial ? { ...told, subject: `${told.subject} (partial)` } : told;
  }, [runs, projects, partial]);
  const groups = useMemo(() => outcomeByGroup(runs, projects), [runs, projects]);
  const attention = useMemo(() => dashboardLists(rows).attention, [rows]);

  const nothingRan = rows.length === 0;
  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {isFiltered(filter) ? (
        <FilterStrip
          filter={filter}
          shown={scoped.length}
          total={rows.length}
          onClear={() => setFilter(NO_FILTER)}
        />
      ) : null}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="space-y-8 px-6 py-6">
          <Verdict verdict={verdict} onOpenRuns={onOpenRuns} />
          {/* Phones have no side bar on screen: its first list sits under the verdict (L01-8). */}
          {attention.length > 0 ? (
            <section
              aria-label="Needs attention"
              className="-mx-6 border-y border-border sm:hidden"
            >
              <h3 className="px-6 pt-2 pb-1 text-micro font-semibold uppercase tracking-wide text-muted-foreground">
                Needs attention · {attention.length}
              </h3>
              <RunList runs={attention} more="more in Runs" empty="" />
            </section>
          ) : null}
          {nothingRan ? (
            <FirstSteps
              projects={projects}
              onNewProject={onNewProject}
              onOpenRuns={() => onOpenRuns()}
            />
          ) : (
            <>
              <Gauges
                runs={runs}
                rows={scoped}
                partial={partial}
                onOpenRuns={onOpenRuns}
                label="Workspace gauges"
              />
              <ActivityPanel
                rows={byBackend}
                inventoryBlocked={inventoryBlocked}
                selection={filter.window}
                onSelect={(window) => setFilter((current) => ({ ...current, window }))}
              />
              <div className="grid min-w-0 gap-x-12 gap-y-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
                <GaugeSection title="Outcome by project" readout="latest attempt of each run">
                  {groups.length === 0 ? (
                    <EmptyLine>No runs in this view.</EmptyLine>
                  ) : (
                    <>
                      <MixChart
                        groups={groups}
                        label="Outcome by project"
                        onPick={onPreviewProject}
                        wording={RUN_WORDING}
                      />
                      <StatusGlyphLegend className="pt-4" />
                    </>
                  )}
                </GaugeSection>
                <GaugeSection title="Backends" readout="attempts · a bar narrows the page">
                  {backends.length === 0 ? (
                    <EmptyLine>No executor recorded yet.</EmptyLine>
                  ) : (
                    <MixChart
                      groups={backends}
                      label="Attempts by backend"
                      selected={filter.backend}
                      wording={ATTEMPT_WORDING}
                      onPick={(backend) =>
                        setFilter((current) => ({
                          ...current,
                          backend: current.backend === backend ? null : backend,
                        }))
                      }
                    />
                  )}
                </GaugeSection>
              </div>
              <GaugeSection title="Duration by project" readout="each finished run">
                <DurationsBy rows={scoped} groupBy="project" />
              </GaugeSection>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
