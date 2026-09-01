import { Loader2, Puzzle } from "lucide-react";
import { type ComponentType, type JSX, useMemo } from "react";
import { listEntityTabs } from "@/app/registry";
import { useDiscoveredFileTypesForRun } from "@/app/state/useDiscoveredFileTypes";
import type {
  ObjectView,
  RendererSnapshot,
  RunSummary,
  Selection,
  WorkspaceSnapshot,
} from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import type { EntityTabContribution, FileTypeContribution } from "@/lib/contribution-types";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";
import type { WorkspaceRunRow } from "../types";

type PluginTabContribution = Pick<
  EntityTabContribution | FileTypeContribution,
  "id" | "value" | "label" | "Icon"
>;

export interface RunPluginAction {
  id: string;
  value: ObjectView;
  label: string;
  Icon?: ComponentType<React.SVGProps<SVGSVGElement>>;
}

const toExecutorInfo = (run: WorkspaceRunRow): Record<string, string> =>
  Object.fromEntries(
    Object.entries({
      backend: run.backend,
      cluster: run.cluster,
      cluster_name: run.cluster,
      scheduler: run.scheduler,
      target: run.target,
      profile: run.profile,
      scheduler_job_id: run.latestSchedulerJobId,
    }).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string" && entry[1] !== "",
    ),
  );

/**
 * The workspace-runs endpoint is intentionally independent from the lazy
 * project tree. Build the minimal catalog row required by plugin matchers so a
 * Molq action can appear before its project branch has ever been expanded.
 */
export const runSummaryForPluginMatching = (run: WorkspaceRunRow): RunSummary => ({
  id: run.id,
  name: run.name,
  status: run.status as RunSummary["status"],
  summary: "",
  updatedAt: run.finishedAt ?? run.createdAt,
  projectId: run.projectId,
  experimentId: run.experimentId,
  executorInfo: toExecutorInfo(run),
  profile: run.profile,
  configHash: null,
  parameters: run.parameters,
  results: {},
  workflowSource: null,
  workflowSnapshot: null,
  startedAt: run.executions.find((execution) => execution.startedAt)?.startedAt ?? null,
  finishedAt: run.finishedAt,
  executionHistory: run.executions.map((execution) => ({
    executionId: execution.executionId,
    startedAt: execution.startedAt,
    finishedAt: execution.finishedAt,
    status: execution.status,
    schedulerJobId: execution.schedulerJobId,
  })),
  errorMessage: null,
});

const isObjectView = (value: string): value is ObjectView =>
  /^[a-z0-9][a-z0-9:_-]{0,63}$/i.test(value);

export const collectRunPluginActions = (
  entityTabs: readonly PluginTabContribution[],
  fileTabs: readonly PluginTabContribution[],
): RunPluginAction[] => {
  const actions = new Map<string, RunPluginAction>();
  for (const contribution of [...entityTabs, ...fileTabs]) {
    if (!isObjectView(contribution.value)) continue;
    actions.set(contribution.value, {
      id: contribution.id,
      value: contribution.value,
      label: contribution.label,
      Icon: contribution.Icon,
    });
  }
  return [...actions.values()];
};

interface RunPluginActionsProps {
  run: WorkspaceRunRow;
  snapshot: WorkspaceSnapshot;
  onOpenTab: (view: ObjectView) => void;
}

/** Contextual launcher for run plugins; heavy visualizers stay in the center workspace. */
export const RunPluginActions = ({
  run,
  snapshot,
  onOpenTab,
}: RunPluginActionsProps): JSX.Element | null => {
  const contributionGeneration = useContributionGeneration();
  const preferencesGeneration = usePluginPreferencesGeneration();
  const coords = useMemo(
    () => ({ projectId: run.projectId, experimentId: run.experimentId, runId: run.id }),
    [run.experimentId, run.id, run.projectId],
  );
  const { discovered, loading } = useDiscoveredFileTypesForRun(coords, "run");

  const selection = useMemo<Selection>(() => ({ objectType: "run", objectId: run.id }), [run.id]);
  const hostSnapshot = useMemo<RendererSnapshot>(
    () => ({
      ...snapshot,
      runs: [
        ...snapshot.runs.filter((item) => item.id !== run.id),
        runSummaryForPluginMatching(run),
      ],
    }),
    [run, snapshot],
  );

  const actions = useMemo(() => {
    void contributionGeneration;
    void preferencesGeneration;
    const entityTabs = listEntityTabs("run", { selection, snapshot: hostSnapshot });
    return collectRunPluginActions(
      entityTabs,
      discovered.map((item) => item.contribution),
    );
  }, [contributionGeneration, discovered, hostSnapshot, preferencesGeneration, selection]);

  if (actions.length === 0 && !loading) return null;

  return (
    <fieldset className="flex min-w-0 items-center gap-1 border-0 p-0">
      <legend className="sr-only">Run tools</legend>
      <span className="mr-1 text-micro text-muted-foreground">Tools</span>
      {actions.map((action) => {
        const Icon = action.Icon ?? Puzzle;
        return (
          <WorkbenchIconAction
            key={action.id}
            label={`Open ${action.label}`}
            size="compact"
            onClick={() => onOpenTab(action.value)}
          >
            <Icon className="size-3.5" aria-hidden />
          </WorkbenchIconAction>
        );
      })}
      {loading ? (
        <Loader2
          className="mol-motion-progress-spin ml-1 size-3 text-muted-foreground"
          aria-label="Discovering run tools"
        />
      ) : null}
    </fieldset>
  );
};
