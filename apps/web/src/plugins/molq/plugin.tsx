import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { Server } from "lucide-react";
import { lazy } from "react";
import { SCHEDULER_FILES } from "./job";

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
const MolqRunView = lazy(() =>
  import("./MolqRunView").then((module) => ({ default: module.MolqRunView })),
);

const molqPlugin: MolabPluginModule = {
  id: "molq",
  name: "Molq",
  version: "1.0.0",
  description: "Molq run view (job and scheduler files) and execution columns for molq backends.",
  activate: (api: PluginAPI) => {
    // A run view applies by files: a Molq submission stages its scheduler
    // evidence under the attempt's `jobs/`, so the view exists exactly then.
    api.runViews.register({
      id: "molq",
      label: "Molq",
      icon: Server,
      order: 30,
      files: SCHEDULER_FILES,
      Component: MolqRunView,
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
