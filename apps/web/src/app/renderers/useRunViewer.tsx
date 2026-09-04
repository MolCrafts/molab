/**
 * useRunViewer — the shared state core behind both run viewers.
 *
 * `RunViewer` (the default run renderer) and `MolqRunViewer` (the molq-backend
 * override) draw very different chrome but drive it from identical state: run
 * resolution off the snapshot, the active-tab sync, lazy stdout/stderr fetching
 * per execution, and the cancel + copy-id handlers. That logic lives
 * here once; each component keeps only its own layout. Run-asset counts and the
 * file-type discovery tabs are RunViewer-only and stay in that component.
 *
 * All hooks run unconditionally (run may be null — effects guard on its id), so
 * callers can still early-return their own "run not found" chrome afterwards.
 */

import { type ReactNode, useEffect, useMemo, useState } from "react";
import { runsApi } from "@/api";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import { listEntityTabs } from "@/app/registry";
import { formatDuration } from "@/app/renderers/dashboardData";
import { canCancel, canHarvest, isTerminalStatus } from "@/app/runs/runLifecycle";
import { useInspectedTask } from "@/app/state/inspectedTask";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererSnapshot, ScopedRendererProps, WorkspaceSnapshot } from "@/app/types";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { Code as InlineCode } from "@/components/ui/code";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { usePluginPreferencesGeneration } from "@/plugins/preferences";

type RunRow = WorkspaceSnapshot["runs"][number];
type RunLogs = { stdout?: string | null; stderr?: string | null } | null;
export type RunRendererProps = ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows"
>;

export interface UseRunViewer {
  run: RunRow | null;
  project: WorkspaceSnapshot["projects"][number] | undefined;
  experiment: WorkspaceSnapshot["experiments"][number] | undefined;
  workflow: WorkspaceSnapshot["workflows"][number] | undefined;
  selectedRunId: string;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  logs: RunLogs;
  logsError: string | null;
  outputs: ExecutionOutputsResponse | null;
  selectedExecutionId: string | null;
  setSelectedExecutionId: (id: string | null) => void;
  duration: string | null;
  attemptCount: number;
  parameterEntries: [string, unknown][];
  resultEntries: [string, unknown][];
  /** True for succeeded/failed/cancelled/skipped. */
  isTerminal: boolean;
  /** Backend-accepted harvest statuses (not skipped). */
  isHarvestable: boolean;
  runTabContributions: ReturnType<typeof listEntityTabs>;
  inspectTask: ReturnType<typeof useInspectedTask>["inspectTask"];
  setSelection: ReturnType<typeof useNavigationState>["setSelection"];
  handleCopyRunId: () => void;
  handleCancelRun: () => Promise<void>;
  confirmDialog: ReactNode;
  alertDialog: ReactNode;
}

export const useRunViewer = (props: RunRendererProps): UseRunViewer => {
  const { selection, snapshot, onRefresh } = props;
  const { setSelection } = useNavigationState(snapshot);
  const { inspectTask } = useInspectedTask();
  const [logs, setLogs] = useState<RunLogs>(null);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<ExecutionOutputsResponse | null>(null);
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  // User-disabled plugins drop their entity tabs without a page reload.
  const pluginPrefsGeneration = usePluginPreferencesGeneration();
  const contributionGeneration = useContributionGeneration();
  // Filter plugin tabs (e.g. molq) by contribution.matches when present.
  const runTabContributions = useMemo(() => {
    void pluginPrefsGeneration;
    void contributionGeneration;
    return listEntityTabs("run", {
      selection: props.selection,
      snapshot: props.snapshot as RendererSnapshot,
    });
  }, [props.selection, props.snapshot, pluginPrefsGeneration, contributionGeneration]);
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();

  const run = useMemo(
    () => snapshot.runs.find((item) => item.id === selection.objectId) ?? null,
    [snapshot.runs, selection.objectId],
  );

  const requestedTab =
    selection.objectType === "run" ? (selection.objectView ?? "overview") : "overview";
  const selectedRunId = selection.objectId;
  const [activeTab, setActiveTab] = useState<string>(requestedTab);

  useEffect(() => {
    if (selectedRunId) {
      setActiveTab(requestedTab);
    }
  }, [requestedTab, selectedRunId]);

  const runProjectId = run?.projectId;
  const runExperimentId = run?.experimentId;
  const runId = run?.id;

  useEffect(() => {
    let cancelled = false;
    setLogsError(null);

    if (!runId || !runProjectId || !runExperimentId || !selectedExecutionId) {
      setLogs(null);
      setOutputs(null);
      return;
    }

    setLogs(null);
    setOutputs(null);
    runsApi
      .getExecutionOutputs(runProjectId, runExperimentId, runId, selectedExecutionId)
      .then((response) => {
        if (!cancelled) {
          setOutputs(response);
          setLogs({ stdout: response.stdout, stderr: response.stderr });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setLogsError(error instanceof Error ? error.message : "Failed to load logs");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [runProjectId, runExperimentId, runId, selectedExecutionId]);

  useEffect(() => {
    setSelectedExecutionId(null);
  }, [runId]);

  const project = run ? snapshot.projects.find((item) => item.id === run.projectId) : undefined;
  const experiment = run
    ? snapshot.experiments.find((item) => item.id === run.experimentId)
    : undefined;
  const workflow =
    run && experiment
      ? snapshot.workflows.find(
          (item) =>
            item.experimentId === experiment.id &&
            (item.name === experiment.workflowFile || item.id === experiment.workflowFile),
        )
      : undefined;

  const duration = run ? formatDuration(run.startedAt, run.finishedAt) : null;
  const attemptCount = run?.executionHistory.length ?? 0;
  const parameterEntries = Object.entries(run?.parameters ?? {});
  const resultEntries = Object.entries(outputs?.results ?? {});
  const isTerminal = run ? isTerminalStatus(run.status) : true;
  const isHarvestable = run ? canHarvest(run.status) : false;

  const handleCopyRunId = (): void => {
    if (!run) return;
    void navigator.clipboard.writeText(run.id);
  };

  const handleCancelRun = async (): Promise<void> => {
    const execution = run?.executionHistory.find(
      (item) => item.executionId === selectedExecutionId,
    );
    if (!run || !execution || !canCancel(execution.status)) return;
    const confirmed = await confirm({
      title: "Cancel execution?",
      description: (
        <>
          Stop{" "}
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">
            {execution.executionId}
          </InlineCode>
          ?
        </>
      ),
      confirmLabel: "Cancel",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await runsApi.cancelExecution(
        run.projectId,
        run.experimentId,
        run.id,
        execution.executionId,
      );
      onRefresh();
    } catch (error) {
      console.error("Failed to cancel run:", error);
      void alert({
        title: "Cancel failed",
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  return {
    run,
    project,
    experiment,
    workflow,
    selectedRunId,
    activeTab,
    setActiveTab,
    logs,
    logsError,
    outputs,
    selectedExecutionId,
    setSelectedExecutionId,
    duration,
    attemptCount,
    parameterEntries,
    resultEntries,
    isTerminal,
    isHarvestable,
    runTabContributions,
    inspectTask,
    setSelection,
    handleCopyRunId,
    handleCancelRun,
    confirmDialog,
    alertDialog,
  };
};
