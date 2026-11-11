/**
 * useRunViewer — the run page's state: run resolution off the snapshot, its
 * project / experiment / workflow, the active-tab sync, the selected attempt and
 * its outputs, plugin run tabs, and the stop handler. Logs are not derived here:
 * `RunLogsPanel` follows each stream itself. File-type discovery tabs stay in
 * `RunViewer`.
 *
 * All hooks run unconditionally (run may be null — effects guard on its id), so
 * callers can still early-return their own "run not found" chrome afterwards.
 */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import { usePreview } from "@/app/preview/PreviewContext";
import { executionOutputsQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { ScopedRendererProps, WorkspaceSnapshot } from "@/app/types";

type RunRow = WorkspaceSnapshot["runs"][number];
export type RunRendererProps = ScopedRendererProps<
  "projects" | "experiments" | "runs" | "workflows" | "workspaces" | "assets"
>;

export interface UseRunViewer {
  run: RunRow | null;
  project: WorkspaceSnapshot["projects"][number] | undefined;
  experiment: WorkspaceSnapshot["experiments"][number] | undefined;
  workflow: WorkspaceSnapshot["workflows"][number] | undefined;
  selectedRunId: string;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  /** Why the selected attempt's outputs could not be read. */
  outputsError: string | null;
  outputs: ExecutionOutputsResponse | null;
  selectedExecutionId: string | null;
  /** Make an attempt the page's (it goes into the URL); the latest drops the parameter. */
  setSelectedExecutionId: (id: string | null) => void;
  /** The log line the URL asks Logs to open at. */
  logLine: number | null;
  attemptCount: number;
  inspectTask: (taskId: string, runId: string) => void;
  setSelection: ReturnType<typeof useNavigationState>["setSelection"];
}

/**
 * Which attempt a run opens on: its latest.
 *
 * Every run view (L14) shows one attempt's files, so leaving this unset
 * renders a run with no plugin views at all until the user picks an attempt. The latest attempt is what you watch. The run result is a different
 * thing: the latest sealed success, even when a later attempt is still running.
 */
export const defaultExecutionId = (
  history: readonly { executionId: string }[] | undefined,
): string | null => (history?.length ? history[history.length - 1].executionId : null);

export const useRunViewer = (props: RunRendererProps): UseRunViewer => {
  const { selection, snapshot } = props;
  const { setSelection } = useNavigationState(snapshot);
  const preview = usePreview();
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

  // The page's attempt lives in the URL (`?attempt=e02`), so the breadcrumb,
  // a reload and a shared link all show the same one; absent means the latest.
  const latestExecutionId = defaultExecutionId(run?.executionHistory);
  const requestedAttempt = selection.objectType === "run" ? selection.attemptId : undefined;
  const selectedExecutionId =
    run?.executionHistory.find((execution) => execution.executionId === requestedAttempt)
      ?.executionId ?? latestExecutionId;
  const logLine = selection.objectType === "run" ? (selection.logLine ?? null) : null;
  const setSelectedExecutionId = (executionId: string | null): void => {
    if (!run) return;
    setSelection({
      objectType: "run",
      objectId: run.id,
      objectView: activeTab === "overview" ? undefined : activeTab,
      ...(executionId && executionId !== latestExecutionId ? { attemptId: executionId } : {}),
    });
  };

  const runProjectId = run?.projectId;
  const runExperimentId = run?.experimentId;
  const runId = run?.id;
  const outputsQuery = useQuery({
    ...executionOutputsQueryOptions(
      runProjectId ?? "",
      runExperimentId ?? "",
      runId ?? "",
      selectedExecutionId ?? "",
    ),
    enabled: Boolean(runId && runProjectId && runExperimentId && selectedExecutionId),
    refetchInterval: journalRefetchInterval(
      run?.executionHistory.find((execution) => execution.executionId === selectedExecutionId)
        ?.status,
    ),
    refetchIntervalInBackground: false,
  });
  const outputs = outputsQuery.data ?? null;
  const outputsError = outputsQuery.error
    ? outputsQuery.error instanceof Error
      ? outputsQuery.error.message
      : "Failed to load outputs"
    : null;

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

  const attemptCount = run?.executionHistory.length ?? 0;

  // A task bar or graph node previews the task (L12); ↵ / ↗ opens its page.
  const inspectTask = (taskId: string, runId: string): void => {
    const owner = snapshot.runs.find((item) => item.id === runId) ?? run;
    if (!owner) return;
    preview.preview({
      kind: "task",
      runId: owner.id,
      projectId: owner.projectId,
      experimentId: owner.experimentId,
      taskId,
      ...(owner.id === run?.id && selectedExecutionId ? { executionId: selectedExecutionId } : {}),
    });
  };

  return {
    run,
    project,
    experiment,
    workflow,
    selectedRunId,
    activeTab,
    setActiveTab,
    outputsError,
    outputs,
    selectedExecutionId,
    setSelectedExecutionId,
    logLine,
    attemptCount,
    inspectTask,
    setSelection,
  };
};
