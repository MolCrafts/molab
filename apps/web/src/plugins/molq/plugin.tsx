import type { MolexpPluginModule, PluginAPI } from "@molcrafts/molexp-plugin";
import { ServerCog } from "lucide-react";
import { lazy } from "react";

const MolqExecutionColumn = {
  Cluster: lazy(() =>
    import("./MolqExecutionColumn").then((module) => ({
      default: module.MolqExecutionColumn.Cluster,
    })),
  ),
  SchedulerJob: lazy(() =>
    import("./MolqExecutionColumn").then((module) => ({
      default: module.MolqExecutionColumn.SchedulerJob,
    })),
  ),
};
const MolqExecutionDetail = lazy(() =>
  import("./MolqExecutionDetail").then((module) => ({ default: module.MolqExecutionDetail })),
);
const MolqRunTab = lazy(() =>
  import("./MolqRunTab").then((module) => ({ default: module.MolqRunTab })),
);
const isMolqRun = (
  runId: string,
  runs: Array<{ id: string; executionHistory: Array<{ executor: Record<string, unknown> }> }>,
) => {
  const run = runs.find((item) => item.id === runId);
  return run?.executionHistory.some((execution) => execution.executor.backend === "molq") ?? false;
};

const molqPlugin: MolexpPluginModule = {
  id: "molq",
  name: "Molq",
  version: "1.0.0",
  description: "Scheduler run monitor, Molq tab, and execution columns for molq backends.",
  activate: (api: PluginAPI) => {
    api.entityTabs.register({
      id: "molq:run-tab",
      objectType: "run",
      value: "molq",
      label: "Molq",
      Icon: ServerCog,
      priority: 40,
      matches: (context) => {
        const selection = context.selection as { objectId: string };
        const snapshot = context.snapshot as {
          runs: Array<{
            id: string;
            executionHistory: Array<{ executor: Record<string, unknown> }>;
          }>;
        };
        return isMolqRun(selection.objectId, snapshot.runs);
      },
      Component: MolqRunTab,
    });

    api.execution.registerColumn({
      id: "molq:column:cluster",
      backend: "molq",
      columnId: "cluster",
      header: "Cluster",
      priority: 100,
      Cell: MolqExecutionColumn.Cluster,
    });
    api.execution.registerColumn({
      id: "molq:column:scheduler-job",
      backend: "molq",
      columnId: "scheduler-job",
      header: "Scheduler Job",
      priority: 90,
      Cell: MolqExecutionColumn.SchedulerJob,
    });

    api.execution.registerDetail({
      id: "molq:detail:submission",
      backend: "molq",
      title: "Molq submission",
      priority: 100,
      Component: MolqExecutionDetail,
    });
  },
};

export default molqPlugin;
