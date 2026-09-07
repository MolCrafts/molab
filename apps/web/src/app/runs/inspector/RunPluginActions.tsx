import { Puzzle } from "lucide-react";
import { type ComponentType, type JSX, useMemo } from "react";
import { listEntityTabs } from "@/app/registry";
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
import { runActivityAt, runFinishedAt, runPresentationStatus, runStartedAt } from "../projections";
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

/**
 * The workspace-runs endpoint is intentionally independent from the lazy
 * project tree. Build the minimal catalog row required by plugin matchers so a
 * Molq action can appear before its project branch has ever been expanded.
 */
export const runSummaryForPluginMatching = (run: WorkspaceRunRow): RunSummary => ({
  id: run.id,
  name: run.name,
  path: run.path,
  status: runPresentationStatus(run) as RunSummary["status"],
  summary: "",
  updatedAt: runActivityAt(run),
  projectId: run.projectId,
  experimentId: run.experimentId,
  definitionHash: run.definitionHash,
  experimentRevisionId: run.experimentRevisionId,
  statusSummary: run.statusSummary,
  parameters: run.parameters,
  workflowSource: null,
  workflowSnapshot: null,
  startedAt: runStartedAt(run),
  finishedAt: runFinishedAt(run),
  executionHistory: run.executions.map((execution) => ({
    executionId: execution.executionId,
    mode: execution.mode,
    createdAt: execution.createdAt,
    startedAt: execution.startedAt,
    finishedAt: execution.finishedAt,
    status: execution.status,
    basedOnExecutionId: execution.basedOnExecutionId,
    checkpointArtifactId: execution.checkpointArtifactId,
    executor: {
      ...(execution.backend ? { backend: execution.backend } : {}),
      ...execution.backendMetadata,
    },
    environment: {},
    artifactIds: [],
    error: null,
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
    return collectRunPluginActions(entityTabs, []);
  }, [contributionGeneration, hostSnapshot, preferencesGeneration, selection]);

  if (actions.length === 0) return null;

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
    </fieldset>
  );
};
