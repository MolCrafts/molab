import { FileQuestion, PlayCircle } from "lucide-react";
import { useMemo } from "react";
import { CopyButton, EmptyState, EntityMetric, EntityPage } from "@/app/components/entity";
import { RunExecutionsPanel } from "@/app/renderers/RunExecutionsPanel";
import { RunLogsPanel } from "@/app/renderers/RunLogsPanel";
import { RunOutputsPanel } from "@/app/renderers/run/RunOutputsPanel";
import { RunOverview } from "@/app/renderers/run/RunOverview";
import { useRunViewer } from "@/app/renderers/useRunViewer";
import { POST_DISPATCH_TAB, RunToolbar } from "@/app/runs/RunToolbar";
import { useInvalidate } from "@/app/state/queries/invalidation";
import { useRunAssetsQuery } from "@/app/state/queries/runs";
import { useDiscoveredFileTypesForRun } from "@/app/state/useDiscoveredFileTypes";
import type { ApiAssetResponse, RendererProps } from "@/app/types";

/** Stable empty list so a pending assets query never re-renders the overview. */
const EMPTY_ASSETS: ApiAssetResponse[] = [];

const openKnowledgePath = (
  path: string,
  setSelection: (sel: { objectType: "knowledge"; objectId: string }) => void,
): void => {
  if (!path) {
    setSelection({ objectType: "knowledge", objectId: "" });
    return;
  }
  const rel = path.startsWith("/") ? path.split("/").filter(Boolean).slice(-3).join("/") : path;
  setSelection({ objectType: "knowledge", objectId: rel });
};

export const RunViewer = (props: RendererProps): JSX.Element => {
  const {
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
    runTabContributions,
    inspectTask,
    setSelection,
    handleCancelRun,
    confirmDialog,
    alertDialog,
  } = useRunViewer(props);
  const invalidate = useInvalidate();

  const runCoords = useMemo(
    () =>
      run ? { projectId: run.projectId, experimentId: run.experimentId, runId: run.id } : null,
    [run],
  );
  const { discovered: discoveredPlugins } = useDiscoveredFileTypesForRun(runCoords, "run");
  const runAssetsQuery = useRunAssetsQuery(run?.id ?? null);
  const runAssets: ApiAssetResponse[] = runAssetsQuery.data ?? EMPTY_ASSETS;

  if (!run) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState icon={<FileQuestion className="h-5 w-5" />} title="Run not found" />
      </div>
    );
  }

  const backend = run.executorInfo.backend || "local";

  const overviewContent = (
    <RunOverview
      run={run}
      project={project}
      experiment={experiment}
      workflow={workflow}
      backend={backend}
      duration={duration}
      attemptCount={attemptCount}
      assets={runAssets}
      parameters={parameterEntries}
      results={resultEntries}
      onOpenProject={() => setSelection({ objectType: "project", objectId: run.projectId })}
      onOpenExperiment={() =>
        setSelection({ objectType: "experiment", objectId: run.experimentId })
      }
      onOpenWorkflow={
        workflow
          ? () =>
              setSelection({
                objectType: "workflow",
                objectId: workflow.id,
                workflowId: workflow.id,
              })
          : undefined
      }
    />
  );

  const executionsContent = (
    <RunExecutionsPanel
      run={run}
      workflow={workflow}
      selectedExecutionId={selectedExecutionId}
      onSelectExecution={setSelectedExecutionId}
      onInspectTask={inspectTask}
      onViewLogs={() => setActiveTab("logs")}
      onOpenWorkflow={
        workflow
          ? () =>
              setSelection({
                objectType: "workflow",
                objectId: workflow.id,
                workflowId: workflow.id,
              })
          : undefined
      }
    />
  );

  const selectedExecutionIndex = selectedExecutionId
    ? run.executionHistory.findIndex((rec) => rec.executionId === selectedExecutionId)
    : -1;
  const attemptCountForLabel = run.executionHistory.length;
  let attemptLabel: string;
  if (selectedExecutionIndex >= 0) {
    attemptLabel = `#${selectedExecutionIndex + 1}`;
  } else if (attemptCountForLabel > 0) {
    attemptLabel = `#${attemptCountForLabel}`;
  } else {
    attemptLabel = "latest";
  }

  const logsContent = (
    <div className="flex h-full flex-1 flex-col overflow-hidden bg-background text-foreground">
      <RunLogsPanel
        logs={logs}
        logsError={logsError}
        selectedExecutionId={selectedExecutionId}
        attemptLabel={attemptLabel}
        onViewLatest={() => setSelectedExecutionId(null)}
      />
    </div>
  );

  const outputResults = resultEntries.map(([key, value]) => ({ key, value }));
  const outputsContent = <RunOutputsPanel assets={runAssets} results={outputResults} />;
  const tabs = [
    { value: "overview", label: "Overview", content: overviewContent },
    {
      value: "outputs",
      label:
        runAssets.length + resultEntries.length > 0
          ? `Outputs (${runAssets.length + resultEntries.length})`
          : "Outputs",
      content: outputsContent,
    },
    {
      value: "executions",
      label: attemptCount ? `Executions (${attemptCount})` : "Executions",
      content: executionsContent,
    },
    ...(hasLogs ? [{ value: "logs", label: "Logs", content: logsContent }] : []),
    // Domain tabs (molvis, metrics plugin if metrics.jsonl present, …) — data-driven only.
    ...runTabContributions.map((tab) => {
      const TabComponent = tab.Component;
      return {
        value: tab.value,
        label: tab.label,
        content: activeTab === tab.value ? <TabComponent key={selectedRunId} {...props} /> : null,
      };
    }),
    ...discoveredPlugins.map(({ contribution, files }) => {
      const PluginComponent = contribution.Component;
      return {
        value: contribution.value,
        label: `${contribution.label} (${files.length})`,
        content:
          activeTab === contribution.value ? (
            <PluginComponent key={selectedRunId} {...props} discoveredFiles={files} />
          ) : null,
      };
    }),
  ];

  return (
    <>
      <EntityPage
        icon={PlayCircle}
        title={run.name}
        status={run.status}
        subtitle={run.summary || undefined}
        metrics={
          <>
            <EntityMetric label="duration" value={duration ?? "—"} />
            <EntityMetric label="attempts" value={attemptCount} />
            <EntityMetric label="assets" value={runAssets.length} />
            <EntityMetric label="results" value={resultEntries.length} />
          </>
        }
        actions={
          <>
            <CopyButton value={run.id} label="run ID" />
            <RunToolbar
              projectId={run.projectId}
              experimentId={run.experimentId}
              runId={run.id}
              status={run.status}
              params={run.parameters ?? {}}
              onCancel={handleCancelRun}
              onDispatched={() => setActiveTab(POST_DISPATCH_TAB)}
              onOpenAgent={() =>
                setSelection({
                  objectType: "agent",
                  objectId: "new",
                  scope: {
                    projectId: run.projectId,
                    experimentId: run.experimentId,
                    runId: run.id,
                  },
                })
              }
              onHarvested={(path) => {
                void invalidate.afterHarvest({ runId: run.id });
                if (path) openKnowledgePath(path, setSelection);
              }}
            />
          </>
        }
        activeTab={activeTab}
        onActiveTabChange={setActiveTab}
        tabs={tabs}
      />
      {confirmDialog}
      {alertDialog}
    </>
  );
};
