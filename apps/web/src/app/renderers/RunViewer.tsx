import { FileQuestion, PlayCircle } from "lucide-react";
import { useMemo } from "react";
import { EmptyState, EntityPage } from "@/app/components/entity";
import { LazySurface } from "@/app/layout/LazySurface";
import { RunExecutionsPanel } from "@/app/renderers/RunExecutionsPanel";
import { RunOverview } from "@/app/renderers/run/RunOverview";
import { type RunRendererProps, useRunViewer } from "@/app/renderers/useRunViewer";
import { RunToolbar } from "@/app/runs/RunToolbar";
import { useDiscoveredFileTypesForRun } from "@/app/state/useDiscoveredFileTypes";
import type { RendererProps } from "@/app/types";
import { pluginTabLabel } from "@/lib/plugin-tab-label";
import { usePluginTabBadgeCounts } from "@/lib/use-plugin-tab-badge-counts";

export const RunViewer = (props: RunRendererProps): JSX.Element => {
  const {
    run, workflow, selectedRunId, activeTab, setActiveTab, outputs, logsError,
    selectedExecutionId, setSelectedExecutionId, attemptCount, parameterEntries,
    runTabContributions, inspectTask, setSelection, handleCancelRun, confirmDialog, alertDialog,
  } = useRunViewer(props);

  const runCoords = useMemo(
    () => run && selectedExecutionId
      ? {
          projectId: run.projectId,
          experimentId: run.experimentId,
          runId: run.id,
          executionId: selectedExecutionId,
        }
      : null,
    [run, selectedExecutionId],
  );
  const { discovered: discoveredPlugins } = useDiscoveredFileTypesForRun(runCoords, "run");
  const tabBadgeCounts = usePluginTabBadgeCounts(discoveredPlugins, runCoords);

  if (!run) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState icon={<FileQuestion className="h-5 w-5" />} title="Run not found" />
      </div>
    );
  }

  const pluginRendererProps: RendererProps = {
    ...(props as RendererProps),
    executionId: selectedExecutionId,
    executionOutputs: outputs,
  };
  const tabs = [
    {
      value: "overview",
      label: "Overview",
      content: <RunOverview run={run} parameters={parameterEntries} />,
    },
    {
      value: "executions",
      label: attemptCount ? `Executions (${attemptCount})` : "Executions",
      content: (
        <RunExecutionsPanel
          run={run}
          workflow={workflow}
          selectedExecutionId={selectedExecutionId}
          onSelectExecution={setSelectedExecutionId}
          onInspectTask={inspectTask}
          outputs={outputs}
          logsError={logsError}
          onPromoted={props.onRefresh}
          onOpenWorkflow={workflow ? () => setSelection({
            objectType: "workflow", objectId: workflow.id, workflowId: workflow.id,
          }) : undefined}
        />
      ),
    },
    ...runTabContributions.map((tab) => {
      const TabComponent = tab.Component;
      return {
        value: tab.value,
        label: tab.label,
        content: activeTab === tab.value ? (
          <LazySurface key={`${selectedRunId}:${selectedExecutionId ?? "none"}`}
            resetKey={`run-tab:${tab.id}:${selectedRunId}:${selectedExecutionId ?? "none"}`}
            loadingTitle={`Loading ${tab.label}…`}>
            <TabComponent {...pluginRendererProps} />
          </LazySurface>
        ) : null,
      };
    }),
    ...discoveredPlugins.map(({ contribution, files }) => {
      const PluginComponent = contribution.Component;
      return {
        value: contribution.value,
        label: pluginTabLabel(contribution.label, files.length,
          Boolean(contribution.resolveTabBadgeCount), tabBadgeCounts[contribution.value]),
        content: activeTab === contribution.value ? (
          <LazySurface key={`${selectedRunId}:${selectedExecutionId}`}
            resetKey={`run-file-tab:${contribution.id}:${selectedRunId}:${selectedExecutionId}`}
            loadingTitle={`Loading ${contribution.label}…`}>
            <PluginComponent {...pluginRendererProps} discoveredFiles={files} />
          </LazySurface>
        ) : null,
      };
    }),
  ];

  return (
    <>
      <EntityPage
        icon={PlayCircle}
        title={run.name}
        actions={
          <RunToolbar
            run={run}
            selectedExecutionId={selectedExecutionId}
            onRefresh={props.onRefresh}
            onCancel={handleCancelRun}
            onDispatched={(executionId) => {
              setSelectedExecutionId(executionId);
              setActiveTab("executions");
            }}
            onOpenAgent={() => setSelection({
              objectType: "agent", objectId: "new",
              scope: { projectId: run.projectId, experimentId: run.experimentId, runId: run.id },
            })}
          />
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
