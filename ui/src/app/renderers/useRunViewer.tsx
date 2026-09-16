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
import { listEntityTabs } from "@/app/registry";
import { formatDuration } from "@/app/renderers/dashboardData";
import { canCancel, canHarvest, isTerminalStatus } from "@/app/runs/runLifecycle";
import { workspaceApi } from "@/app/state/api";
import { useInspectedTask } from "@/app/state/inspectedTask";
import { useInvalidate } from "@/app/state/queries/invalidation";
import { useRunCoords, useRunLogsQuery } from "@/app/state/queries/runs";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps, WorkspaceSnapshot } from "@/app/types";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { Code as InlineCode } from "@/components/ui/code";

type RunRow = WorkspaceSnapshot["runs"][number];
type RunLogs = { stdout?: string | null; stderr?: string | null } | null;

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
  /** Whether to surface the Logs tab (derived from attempts, not a fetch). */
  hasLogs: boolean;
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

export const useRunViewer = (props: RendererProps): UseRunViewer => {
  const { selection, snapshot } = props;
  const { setSelection } = useNavigationState(snapshot);
  const { inspectTask } = useInspectedTask();
  const invalidate = useInvalidate();
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null);
  const runTabContributions = listEntityTabs("run");
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

  // Logs are fetched only when the Logs tab is open. Whether that tab exists is
  // decided from the run's own execution history, not from a speculative fetch
  // — this used to pull stdout/stderr on every run open, on every tab.
  const coords = useRunCoords(run);
  const logsQuery = useRunLogsQuery(coords, selectedExecutionId, {
    enabled: activeTab === "logs",
    isRunning: run?.status === "running",
  });
  const logs: RunLogs = logsQuery.data
    ? { stdout: logsQuery.data.stdout, stderr: logsQuery.data.stderr }
    : null;
  const logsError = logsQuery.error instanceof Error ? logsQuery.error.message : null;

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
  // A run that has executed has log files; asking the server first would
  // reintroduce the eager fetch this tab gating exists to remove.
  const hasLogs = attemptCount > 0;
  const parameterEntries = Object.entries(run?.parameters ?? {});
  const resultEntries = Object.entries(run?.results ?? {});
  const isTerminal = run ? isTerminalStatus(run.status) : true;
  const isHarvestable = run ? canHarvest(run.status) : false;

  const handleCopyRunId = (): void => {
    if (!run) return;
    void navigator.clipboard.writeText(run.id);
  };

  const handleCancelRun = async (): Promise<void> => {
    if (!run || !canCancel(run.status)) return;
    const confirmed = await confirm({
      title: "Cancel run?",
      description: (
        <>
          Stop{" "}
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">
            {run.id}
          </InlineCode>
          ?
        </>
      ),
      confirmLabel: "Cancel",
      destructive: true,
    });
    if (!confirmed) return;
    try {
      await workspaceApi.killRun(run.projectId, run.experimentId, run.id);
      await invalidate.afterRunVerb({
        runId: run.id,
        projectId: run.projectId,
        experimentId: run.experimentId,
      });
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
    hasLogs,
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
