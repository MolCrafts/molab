import { Workflow } from "lucide-react";
import { useState } from "react";
import {
  BarInstrument,
  DashboardCanvas,
  DashboardCard,
  DataTable,
  EmptyState,
  EntityPage,
  OverviewInstruments,
  OverviewList,
  OverviewSurface,
  type StatusCountRollup,
  StatusDistribution,
} from "@/app/components/entity";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { RendererProps } from "@/app/types";
import type { TaskNodeJson } from "@/components/workflow/task-graph-ir";
import { WorkflowGraphViewer } from "@/plugins/workflow/WorkflowGraphViewer";
import { WorkflowSourceViewer } from "@/plugins/workflow/WorkflowSourceViewer";

const taskStatusCounts = (tasks: readonly TaskNodeJson[]): StatusCountRollup => {
  const counts: StatusCountRollup = {
    total: 0,
    running: 0,
    pending: 0,
    succeeded: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const task of tasks) {
    const group = groupForStatus(task.status);
    if (!group) continue;
    counts.total += 1;
    counts[group] += 1;
  }
  return counts;
};

const taskTypeCounts = (tasks: readonly TaskNodeJson[]): { type: string; count: number }[] => {
  const counts = new Map<string, number>();
  for (const task of tasks) {
    const type = task.type || "task";
    counts.set(type, (counts.get(type) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([type, count]) => ({ type, count }))
    .sort((left, right) => right.count - left.count || left.type.localeCompare(right.type));
};

const WorkflowOverviewBody = ({ selection, snapshot }: RendererProps): JSX.Element | null => {
  const workflow = snapshot.workflows.find((w) => w.id === selection.objectId);
  if (!workflow) return null;

  const tasks = workflow.graph?.task_configs ?? [];
  const statuses = taskStatusCounts(tasks);
  const types = taskTypeCounts(tasks);

  return (
    <OverviewSurface>
      <DashboardCanvas>
        {workflow.summary ? (
          <p className="max-w-2xl text-body text-muted-foreground">{workflow.summary}</p>
        ) : null}
        <OverviewInstruments>
          {statuses.total > 0 ? (
            <DashboardCard title="Task status">
              <StatusDistribution counts={statuses} unit="tasks" />
            </DashboardCard>
          ) : null}
          {types.length > 0 ? (
            <DashboardCard title="Task types">
              <BarInstrument
                label="Task types"
                bars={types.map((item) => ({
                  id: item.type,
                  value: item.count,
                  label: item.type,
                  tooltip: `${item.type}: ${item.count}`,
                }))}
              />
            </DashboardCard>
          ) : null}
        </OverviewInstruments>
        <OverviewList title="Tasks">
          <DataTable
            columns={[
              {
                key: "task",
                header: "Task",
                cell: (task) => (
                  <span className="text-body text-foreground">{task.label || task.id}</span>
                ),
              },
              {
                key: "type",
                header: "Type",
                cell: (task) => (
                  <span className="font-mono text-label text-muted-foreground">{task.type}</span>
                ),
              },
            ]}
            data={tasks}
            getRowKey={(task) => task.id}
            getRowLabel={(task) => task.label || task.id}
            empty={<EmptyState title="No tasks yet" />}
          />
        </OverviewList>
      </DashboardCanvas>
    </OverviewSurface>
  );
};

export const WorkflowViewer = (props: RendererProps): JSX.Element => {
  const { selection, snapshot } = props;
  const workflow = snapshot.workflows.find((w) => w.id === selection.objectId);
  const [activeTab, setActiveTab] = useState("graph");

  if (!workflow) {
    return <div className="p-8 text-muted-foreground">Workflow not found.</div>;
  }

  return (
    <EntityPage
      icon={Workflow}
      title={workflow.name}
      activeTab={activeTab}
      onActiveTabChange={setActiveTab}
      tabs={[
        {
          value: "graph",
          label: "Graph",
          content: activeTab === "graph" ? <WorkflowGraphViewer {...props} /> : null,
        },
        { value: "overview", label: "Overview", content: <WorkflowOverviewBody {...props} /> },
        { value: "source", label: "Source", content: <WorkflowSourceViewer {...props} /> },
      ]}
    />
  );
};
