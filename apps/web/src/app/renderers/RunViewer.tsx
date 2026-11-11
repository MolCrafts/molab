/**
 * The run page (Figma L04): views Overview · Params · Attempts (n) · Logs, a
 * rule, then plugin views (L14 `api.runViews`, each in `<RunView>`). The
 * state's primary action and ⋯ sit at the right of the editor tab row. Every
 * view follows one attempt — the page's, kept in the URL, named by the chip at
 * the right end of the views (and the breadcrumb's last segment).
 */

import type { RunAttempt } from "@molcrafts/molab-plugin";
import { RunViewHostProvider } from "@molcrafts/molab-plugin/ui";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  FileQuestion,
  History,
  PlayCircle,
  Puzzle,
  SlidersHorizontal,
  Terminal,
} from "lucide-react";
import { type JSX, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { activeWorkspace, itemFromRunSummary } from "@/app/compare/entries";
import { EmptyState, EntityPage, ViewLabel } from "@/app/components/entity";
import { LazySurface } from "@/app/layout/LazySurface";
import { usePreview } from "@/app/preview/PreviewContext";
import { RunAttemptsPanel } from "@/app/renderers/RunAttemptsPanel";
import { RunLogsPanel } from "@/app/renderers/RunLogsPanel";
import { RunAttemptChip } from "@/app/renderers/run/RunAttemptChip";
import { type OpenInView, RunOverview } from "@/app/renderers/run/RunOverview";
import { RunParams } from "@/app/renderers/run/RunParams";
import { runResultExecution } from "@/app/renderers/run/runStory";
import { useRunViewHost, useRunViews } from "@/app/renderers/run/useRunViews";
import { type RunRendererProps, useRunViewer } from "@/app/renderers/useRunViewer";
import { RunEditorActions } from "@/app/runs/RunEditorActions";
import { runLabel } from "@/app/runs/runTitle";
import { confirmAndStopExecution } from "@/app/runs/stopExecution";
import { experimentWorkflowLabel } from "@/app/state/api";
import { journalRefetchInterval } from "@/app/state/entityQueries";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { matchesMatcher } from "@/lib/file-type-discovery";
import { knowledgeKeys } from "@/plugins/knowledge/queries";

export const RunViewer = (props: RunRendererProps): JSX.Element => {
  const {
    run,
    project,
    experiment,
    workflow,
    selectedRunId,
    activeTab,
    setActiveTab,
    outputs,
    outputsError,
    selectedExecutionId,
    setSelectedExecutionId,
    logLine,
    attemptCount,
    inspectTask,
    setSelection,
  } = useRunViewer(props);
  const preview = usePreview();
  const queryClient = useQueryClient();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();

  // `?new=resume` (a Preview's Resume) opens New attempt with Resume chosen, once.
  const [searchParams, setSearchParams] = useSearchParams();
  const createRequest = searchParams.get("new") === "resume" ? ({ mode: "resume" } as const) : null;
  const clearCreateRequest = useCallback(() => {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.delete("new");
        return next;
      },
      { replace: true },
    );
  }, [setSearchParams]);

  const compareWorkspace = activeWorkspace(props.snapshot.workspaces);
  // From the run page, Compare pins the attempt on screen rather than "latest".
  const compareEntry = useMemo(() => {
    if (!run || !compareWorkspace) return null;
    return {
      ...itemFromRunSummary(run, {
        workspaceKey: compareWorkspace.key,
        workspaceLabel: compareWorkspace.label,
        projectName: project?.name ?? run.projectId,
        experimentName: experiment?.name ?? run.experimentId,
      }),
      executionId: selectedExecutionId,
    };
  }, [run, compareWorkspace, project?.name, experiment?.name, selectedExecutionId]);

  const runCoords = useMemo(
    () =>
      run && selectedExecutionId
        ? {
            projectId: run.projectId,
            experimentId: run.experimentId,
            runId: run.id,
            executionId: selectedExecutionId,
          }
        : null,
    [run, selectedExecutionId],
  );

  // L14: plugin views get the page's attempt from the host, never choose it.
  const baseAttempt = useMemo((): RunAttempt | null => {
    if (!run || !selectedExecutionId) return null;
    const history = run.executionHistory;
    const execution = history.find((item) => item.executionId === selectedExecutionId);
    return {
      projectId: run.projectId,
      experimentId: run.experimentId,
      runId: run.id,
      executionId: selectedExecutionId,
      status: execution?.status ?? "pending",
      isLatest: history.at(-1)?.executionId === selectedExecutionId,
      isRunResult: runResultExecution(history)?.execution.executionId === selectedExecutionId,
      dir: null,
    };
  }, [run, selectedExecutionId]);
  const { tabs: runViewTabs, dir: attemptDir } = useRunViews(baseAttempt);
  const runAttempt = useMemo(
    () => (baseAttempt ? { ...baseAttempt, dir: attemptDir } : null),
    [baseAttempt, attemptDir],
  );
  const openAttemptPath = useCallback(
    (path: string) => {
      if (!attemptDir) return;
      const filePath = `${attemptDir.replace(/\/+$/, "")}/${path}`;
      setSelection({
        objectType: "workspace-file",
        objectId: filePath,
        filePath,
        fileKind: "text",
      });
    },
    [attemptDir, setSelection],
  );
  const openLogsAt = useCallback(
    (line?: number) => {
      if (!run) return;
      setActiveTab("logs");
      setSelection({
        objectType: "run",
        objectId: run.id,
        objectView: "logs",
        ...(selectedExecutionId && selectedExecutionId !== run.executionHistory.at(-1)?.executionId
          ? { attemptId: selectedExecutionId }
          : {}),
        ...(line ? { logLine: line } : {}),
      });
    },
    [run, selectedExecutionId, setActiveTab, setSelection],
  );
  const runViewLinks = useMemo(
    () => ({ openFile: openAttemptPath, openLogs: openLogsAt }),
    [openAttemptPath, openLogsAt],
  );
  const runViewHost = useRunViewHost(runAttempt, runViewLinks);

  if (!run) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState icon={<FileQuestion className="size-icon-lg" />} title="Run not found" />
      </div>
    );
  }

  const history = run.executionHistory;
  const attempt = history.find((item) => item.executionId === selectedExecutionId) ?? null;
  const scope = { runId: run.id, projectId: run.projectId, experimentId: run.experimentId };

  const openView = (value: string, focus: { line?: number } = {}): void => {
    setActiveTab(value);
    setSelection({
      objectType: "run",
      objectId: run.id,
      objectView: value === "overview" ? undefined : value,
      ...(selectedExecutionId && selectedExecutionId !== history.at(-1)?.executionId
        ? { attemptId: selectedExecutionId }
        : {}),
      ...(focus.line ? { logLine: focus.line } : {}),
    });
  };
  const openIn = (file: { name: string; relPath: string }): OpenInView | null => {
    const view = runViewTabs.find(
      ({ contribution }) =>
        contribution.files && matchesMatcher(contribution.files, { ...file, type: "file" }),
    );
    if (view) return { value: view.contribution.id, label: view.contribution.label };
    return null;
  };
  const stop = (execution: (typeof history)[number]): void =>
    void confirmAndStopExecution({ run, execution, confirm, alert, onStopped: props.onRefresh });

  const tabs = [
    {
      value: "overview",
      label: <ViewLabel icon={Activity}>Overview</ViewLabel>,
      content: (
        <RunOverview
          run={run}
          attempt={attempt}
          outputs={outputs}
          openIn={openIn}
          onOpenView={openView}
          onPreviewTask={(taskId) => inspectTask(taskId, run.id)}
          onPreviewRun={(runId) => {
            const sibling = props.snapshot.runs.find((item) => item.id === runId);
            preview.preview({
              kind: "run",
              runId,
              projectId: sibling?.projectId ?? run.projectId,
              experimentId: sibling?.experimentId ?? run.experimentId,
            });
          }}
          onPreviewAsset={(assetId) => preview.preview({ kind: "asset", assetId })}
          onOpenKnowledge={(path) => setSelection({ objectType: "knowledge", objectId: path })}
        />
      ),
    },
    {
      value: "parameters",
      label: <ViewLabel icon={SlidersHorizontal}>Params</ViewLabel>,
      content: (
        <RunParams
          run={run}
          assets={props.snapshot.assets}
          workflowLabel={experiment ? experimentWorkflowLabel(experiment) || null : null}
          onPreviewRun={(runId) => preview.preview({ kind: "run", ...scope, runId })}
          onPreviewAsset={(assetId) => preview.preview({ kind: "asset", assetId })}
        />
      ),
    },
    {
      value: "executions",
      label: (
        <ViewLabel icon={History} count={attemptCount}>
          Attempts
        </ViewLabel>
      ),
      content: (
        <RunAttemptsPanel
          run={run}
          workflow={workflow}
          selectedExecutionId={selectedExecutionId}
          onSelectExecution={setSelectedExecutionId}
          onPreviewExecution={(executionId) =>
            preview.preview({ kind: "attempt", ...scope, executionId })
          }
          onInspectTask={inspectTask}
          outputs={outputs}
          logsError={outputsError}
          onPromoted={props.onRefresh}
          onOpenWorkflow={
            workflow
              ? () =>
                  setSelection({
                    objectType: "experiment",
                    objectId: workflow.experimentId,
                    experimentView: "workflow",
                  })
              : undefined
          }
        />
      ),
    },
    {
      value: "logs",
      label: <ViewLabel icon={Terminal}>Logs</ViewLabel>,
      content: (
        <RunLogsPanel
          key={`${run.id}:${selectedExecutionId ?? "none"}`}
          execution={runCoords}
          live={journalRefetchInterval(attempt?.status) !== false}
          line={logLine}
          onOpenFile={attemptDir ? openAttemptPath : undefined}
        />
      ),
    },
    ...runViewTabs.map(({ contribution, files, count }, index) => {
      const View = contribution.Component;
      return {
        value: contribution.id,
        dividerBefore: index === 0,
        label: (
          <ViewLabel icon={contribution.icon ?? Puzzle} count={count ?? undefined}>
            {contribution.label}
          </ViewLabel>
        ),
        content:
          runAttempt && runViewHost ? (
            <LazySurface
              suspense={false}
              key={`${selectedRunId}:${selectedExecutionId ?? "none"}`}
              resetKey={`run-view:${contribution.id}:${selectedRunId}:${selectedExecutionId ?? "none"}`}
              loadingTitle={`Loading ${contribution.label}…`}
            >
              <RunViewHostProvider value={runViewHost}>
                <View attempt={runAttempt} files={files} />
              </RunViewHostProvider>
            </LazySurface>
          ) : null,
      };
    }),
  ];

  return (
    <>
      <EntityPage
        icon={PlayCircle}
        title={runLabel(run)}
        actions={
          <>
            <span className="sm:hidden">
              <RunAttemptChip
                history={run.executionHistory}
                selected={selectedExecutionId}
                onSelect={setSelectedExecutionId}
              />
            </span>
            <RunEditorActions
              run={run}
              pageExecutionId={selectedExecutionId}
              compareEntry={compareEntry}
              onStop={stop}
              onCreated={(executionId) => {
                props.onRefresh();
                // The new attempt is the latest: the page follows it on Overview.
                void executionId;
                setActiveTab("overview");
                setSelection({ objectType: "run", objectId: run.id });
              }}
              onOpenLogs={() => openView("logs")}
              onHarvested={(path) => {
                void queryClient.invalidateQueries({ queryKey: knowledgeKeys.lists() });
                if (path) setSelection({ objectType: "knowledge", objectId: path });
              }}
              request={createRequest}
              onRequestHandled={clearCreateRequest}
            />
          </>
        }
        activeTab={activeTab}
        onActiveTabChange={(value) => openView(value)}
        tabs={tabs}
        tabsTrailing={
          <RunAttemptChip
            history={run.executionHistory}
            selected={selectedExecutionId}
            onSelect={setSelectedExecutionId}
          />
        }
      />
      {confirmDialog}
      {alertDialog}
    </>
  );
};
