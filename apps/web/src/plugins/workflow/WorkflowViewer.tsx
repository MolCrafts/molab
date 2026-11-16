import { Hash, Shapes, Workflow } from "lucide-react";
import { useState } from "react";
import {
  type CountBar,
  CountBars,
  DataTable,
  DialLegend,
  EmptyState,
  EntityPage,
  GaugeSection,
  Instrument,
  InstrumentStrip,
  InventoryCanvas,
  OverviewCanvas,
  OverviewSurface,
  SuccessDial,
  Tally,
} from "@/app/components/entity";
import { countStatuses, type StatusCounts } from "@/app/status/vocabulary";
import type { RendererProps } from "@/app/types";
import type { TaskNodeJson } from "@/components/workflow/task-graph-ir";
import { WorkflowGraphViewer } from "@/plugins/workflow/WorkflowGraphViewer";

const taskStatusCounts = (tasks: readonly TaskNodeJson[]): StatusCounts =>
  countStatuses(tasks.map((task) => task.status));

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

const TaskTable = ({ tasks }: { tasks: readonly TaskNodeJson[] }): JSX.Element => (
  <OverviewSurface>
    <InventoryCanvas>
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
        data={[...tasks]}
        getRowKey={(task) => task.id}
        getRowLabel={(task) => task.label || task.id}
        empty={<EmptyState title="No tasks yet" />}
      />
    </InventoryCanvas>
  </OverviewSurface>
);

const WorkflowOverviewBody = ({
  tasks,
  summary,
  onOpenTasks,
}: {
  tasks: readonly TaskNodeJson[];
  summary: string | null | undefined;
  onOpenTasks: () => void;
}): JSX.Element => {
  const statuses = taskStatusCounts(tasks);
  const types = taskTypeCounts(tasks);
  const bars: CountBar[] = types.map((item) => ({
    key: item.type,
    label: item.type,
    value: item.count,
    readout: `${item.count} ${item.count === 1 ? "task" : "tasks"}`,
    tip: `${item.type}: ${item.count} of ${tasks.length} tasks`,
  }));

  if (tasks.length === 0) {
    return (
      <OverviewCanvas>
        <EmptyState title="No tasks yet" description="This workflow's graph has no tasks." />
      </OverviewCanvas>
    );
  }

  return (
    <OverviewCanvas>
      {summary ? <p className="max-w-[65ch] text-body text-muted-foreground">{summary}</p> : null}
      <InstrumentStrip label="Workflow gauges" lead={statuses.total > 0}>
        {statuses.total > 0 ? (
          <Instrument title="State" inline>
            <span className="flex min-w-0 items-center gap-4">
              <SuccessDial counts={statuses} />
              <DialLegend counts={statuses} unit={["task", "tasks"]} />
            </span>
          </Instrument>
        ) : null}
        <Instrument
          title="Tasks"
          figure={tasks.length}
          caption={
            <Tally
              icon={Shapes}
              value={types.length}
              label={`${types.length} task ${types.length === 1 ? "type" : "types"}`}
            />
          }
          onSelect={onOpenTasks}
          selectHint="Tasks"
          selectLabel={`${tasks.length} tasks. Open the list`}
        />
        <Instrument
          title="Top type"
          figure={types[0]?.type ?? "—"}
          caption={
            types[0] ? (
              <Tally
                icon={Hash}
                value={`${types[0].count}/${tasks.length}`}
                label={`${types[0].count} of ${tasks.length} tasks`}
              />
            ) : undefined
          }
        />
      </InstrumentStrip>
      <GaugeSection title="Tasks by type">
        <CountBars bars={bars} label="Number of tasks of each type" onPick={onOpenTasks} />
      </GaugeSection>
    </OverviewCanvas>
  );
};

export const WorkflowViewer = (props: RendererProps): JSX.Element => {
  const { selection, snapshot } = props;
  const workflow = snapshot.workflows.find((w) => w.id === selection.objectId);
  const [activeTab, setActiveTab] = useState("graph");

  if (!workflow) {
    return <div className="p-8 text-muted-foreground">Workflow not found.</div>;
  }

  const tasks = workflow.graph?.task_configs ?? [];

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
        {
          value: "overview",
          label: "Overview",
          content: (
            <WorkflowOverviewBody
              tasks={tasks}
              summary={workflow.summary}
              onOpenTasks={() => setActiveTab("tasks")}
            />
          ),
        },
        {
          value: "tasks",
          label: tasks.length > 0 ? `Tasks (${tasks.length})` : "Tasks",
          content: <TaskTable tasks={tasks} />,
        },
      ]}
    />
  );
};
