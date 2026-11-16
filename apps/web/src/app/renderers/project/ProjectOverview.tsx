/**
 * Project Overview (Figma L02-1, L02-6): the experiment Overview one level up.
 * A verdict over every run of the project — whose counts open the workspace
 * Runs filtered to this project — and one line naming the experiment the runs
 * needing attention sit in; then the three gauges, the outcome by experiment
 * (a bar previews its experiment) and the duration by experiment. A project
 * with nothing run says what to do first.
 */

import { type JSX, useMemo } from "react";
import {
  GaugeSection,
  MixChart,
  OverviewCanvas,
  StatusGlyphLegend,
  StatusIcon,
} from "@/app/components/entity";
import { DurationsBy } from "@/app/dashboard/dashboardWidgets";
import { Gauges, Verdict } from "@/app/renderers/experiment/ExperimentOverview";
import { outcomeByGroup, type ScopeRun, scopeVerdict } from "@/app/renderers/scopeStory";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { ExperimentSummary } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { WorkbenchOperationState } from "@/components/workbench";

const RUN_WORDING = { unit: ["run", "runs"] } as const;

export interface ProjectOverviewProps {
  experiments: readonly ExperimentSummary[];
  /** Each run of the project with its latest status (from the run inventory). */
  runs: readonly ScopeRun[];
  /** The same runs as the workspace inventory has them (attempt rows), for gauges and durations. */
  rows: readonly WorkspaceRunRow[];
  partial: boolean;
  /** The run inventory has not answered yet. */
  loading: boolean;
  onOpenRuns: (filter?: string) => void;
  onPreviewExperiment: (experimentId: string) => void;
  onOpenExperiment: (experimentId: string) => void;
  onNewExperiment: () => void;
}

/** Nothing has run: what is there, in order, with the one action each needs. */
const FirstSteps = ({
  experiments,
  onOpenExperiment,
  onNewExperiment,
}: Pick<
  ProjectOverviewProps,
  "experiments" | "onOpenExperiment" | "onNewExperiment"
>): JSX.Element => (
  <ol
    aria-label="What this project needs"
    className="max-w-[40rem] divide-y divide-border border-b border-border"
  >
    <li className="flex min-h-11 items-center gap-3 py-1">
      <StatusIcon
        status={experiments.length > 0 ? "succeeded" : "pending"}
        className="size-icon shrink-0"
      />
      <span className="min-w-0 flex-1">
        <span className="block text-body text-foreground">Experiments</span>
        <span className="block truncate text-label text-muted-foreground">
          {experiments.length > 0
            ? experiments.map((experiment) => experiment.name).join(" · ")
            : "None yet · an experiment holds one workflow and its runs"}
        </span>
      </span>
      <DialogButton kind="secondary" onClick={onNewExperiment}>
        New experiment…
      </DialogButton>
    </li>
    {experiments.length > 0 ? (
      <li className="flex min-h-11 items-center gap-3 py-1">
        <StatusIcon status="pending" className="size-icon shrink-0" />
        <span className="min-w-0 flex-1">
          <span className="block text-body text-foreground">Runs</span>
          <span className="block truncate text-label text-muted-foreground">
            None yet · an experiment starts them
          </span>
        </span>
        <DialogButton kind="secondary" onClick={() => onOpenExperiment(experiments[0]?.id ?? "")}>
          Open {experiments.length === 1 ? (experiments[0]?.name ?? "experiment") : "experiment"}
        </DialogButton>
      </li>
    ) : null}
  </ol>
);

export const ProjectOverview = ({
  experiments,
  runs,
  rows,
  partial,
  loading,
  onOpenRuns,
  onPreviewExperiment,
  onOpenExperiment,
  onNewExperiment,
}: ProjectOverviewProps): JSX.Element => {
  const named = useMemo(
    () => experiments.map((experiment) => ({ id: experiment.id, name: experiment.name })),
    [experiments],
  );
  const verdict = useMemo(() => scopeVerdict(runs, named), [runs, named]);
  const groups = useMemo(() => outcomeByGroup(runs, named), [runs, named]);

  return (
    <OverviewCanvas>
      {loading ? (
        <WorkbenchOperationState
          kind="loading"
          density="compact"
          title="Loading runs…"
          skeletonRows={3}
        />
      ) : (
        <Verdict verdict={verdict} onOpenRuns={onOpenRuns} />
      )}
      {loading ? null : runs.length === 0 ? (
        <FirstSteps
          experiments={experiments}
          onOpenExperiment={onOpenExperiment}
          onNewExperiment={onNewExperiment}
        />
      ) : (
        <>
          <Gauges
            runs={runs}
            rows={rows}
            partial={partial}
            onOpenRuns={onOpenRuns}
            label="Project gauges"
          />
          <div className="grid min-w-0 gap-x-12 gap-y-8 lg:grid-cols-2">
            <GaugeSection title="Outcome by experiment" readout="latest attempt of each run">
              <MixChart
                groups={groups}
                label="Outcome by experiment"
                onPick={onPreviewExperiment}
                wording={RUN_WORDING}
              />
              <StatusGlyphLegend className="pt-4" />
            </GaugeSection>
            <GaugeSection title="Duration by experiment" readout="each finished run">
              <DurationsBy rows={rows} groupBy="experiment" />
            </GaugeSection>
          </div>
        </>
      )}
    </OverviewCanvas>
  );
};
