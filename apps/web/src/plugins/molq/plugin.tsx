import { ServerCog } from "lucide-react";
import { lazy } from "react";
import {
  registerEntityTabContribution,
  registerExecutionColumn,
  registerExecutionDetail,
} from "@/app/registry";
import type { UiPluginModule } from "@/plugins/types";

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

const molqPlugin: UiPluginModule = {
  id: "molq",
  name: "Molq",
  description: "Scheduler run monitor, Molq tab, and execution columns for molq backends.",
  userToggleable: true,
  register: () => {
    registerEntityTabContribution({
      id: "molq:run-tab",
      objectType: "run",
      value: "molq",
      label: "Molq",
      Icon: ServerCog,
      priority: 40,
      matches: ({ selection, snapshot }) => isMolqRun(selection.objectId, snapshot.runs),
      Component: MolqRunTab,
    });

    registerExecutionColumn({
      id: "molq:column:cluster",
      backend: "molq",
      columnId: "cluster",
      header: "Cluster",
      priority: 100,
      Cell: MolqExecutionColumn.Cluster,
    });
    registerExecutionColumn({
      id: "molq:column:scheduler-job",
      backend: "molq",
      columnId: "scheduler-job",
      header: "Scheduler Job",
      priority: 90,
      Cell: MolqExecutionColumn.SchedulerJob,
    });

    registerExecutionDetail({
      id: "molq:detail:submission",
      backend: "molq",
      title: "Molq submission",
      priority: 100,
      Component: MolqExecutionDetail,
    });
  },
};

export default molqPlugin;
