import type {
  AssetSummary,
  ExperimentSummary,
  ProjectSummary,
  RendererSnapshot,
  RunSummary,
  Selection,
  SemanticObjectType,
  WorkflowSummary,
} from "@/app/types";

export interface MetadataField {
  label: string;
  value: string;
}

const findProject = (snapshot: RendererSnapshot, id: string): ProjectSummary | null => {
  return snapshot.projects.find((project) => project.id === id) ?? null;
};

const findExperiment = (snapshot: RendererSnapshot, id: string): ExperimentSummary | null => {
  return snapshot.experiments.find((experiment) => experiment.id === id) ?? null;
};

const findRun = (snapshot: RendererSnapshot, id: string): RunSummary | null => {
  return snapshot.runs.find((run) => run.id === id) ?? null;
};

const findAsset = (snapshot: RendererSnapshot, id: string): AssetSummary | null => {
  return snapshot.assets.find((asset) => asset.id === id) ?? null;
};

const findWorkflow = (snapshot: RendererSnapshot, id: string): WorkflowSummary | null => {
  return snapshot.workflows.find((workflow) => workflow.id === id) ?? null;
};

const emptyFields = (objectType: SemanticObjectType, objectId: string): MetadataField[] => {
  return [
    { label: "Object Type", value: objectType },
    { label: "Object ID", value: objectId },
    { label: "Status", value: "Missing in snapshot" },
  ];
};

export const buildMetadataFields = (
  selection: Selection,
  snapshot: RendererSnapshot,
): MetadataField[] => {
  const lookupByType: Record<SemanticObjectType, () => MetadataField[]> = {
    project: () => {
      const project = findProject(snapshot, selection.objectId);
      if (!project) {
        return emptyFields("project", selection.objectId);
      }
      const fields: MetadataField[] = [
        { label: "Name", value: project.name },
        { label: "Project ID", value: project.id },
        { label: "Status", value: project.status },
        { label: "Updated", value: project.updatedAt },
      ];
      if (project.summary) {
        fields.push({ label: "Summary", value: project.summary });
      }
      if (project.workspaceKey) {
        fields.push({ label: "Workspace", value: project.workspaceKey });
      }
      return fields;
    },
    experiment: () => {
      const experiment = findExperiment(snapshot, selection.objectId);
      if (!experiment) {
        return emptyFields("experiment", selection.objectId);
      }
      const fields: MetadataField[] = [
        { label: "Name", value: experiment.name },
        { label: "Experiment ID", value: experiment.id },
        { label: "Status", value: experiment.status },
        { label: "Updated", value: experiment.updatedAt },
      ];
      if (experiment.summary) {
        fields.push({ label: "Summary", value: experiment.summary });
      }
      if (
        experiment.workflowFile &&
        !experiment.workflowFile.trim().startsWith("{") &&
        !experiment.workflowFile.trim().startsWith("[")
      ) {
        fields.push({ label: "Workflow file", value: experiment.workflowFile });
      }
      if (experiment.workflowKind) {
        fields.push({ label: "Workflow kind", value: experiment.workflowKind });
      }
      fields.push({ label: "Project ID", value: experiment.projectId });
      return fields;
    },
    run: () => {
      const run = findRun(snapshot, selection.objectId);
      if (!run) {
        return emptyFields("run", selection.objectId);
      }
      // Parent project/experiment/workflow live under inspector Lineage — ids
      // stay here only as copyable coordinates, not as the navigation surface.
      const fields: MetadataField[] = [
        { label: "Name", value: run.name || run.id },
        { label: "Run ID", value: run.id },
        { label: "Status", value: run.status },
        { label: "Updated", value: run.updatedAt },
      ];
      if (run.summary) {
        fields.push({ label: "Summary", value: run.summary });
      }
      if (run.startedAt) {
        fields.push({ label: "Started", value: run.startedAt });
      }
      if (run.finishedAt) {
        fields.push({ label: "Finished", value: run.finishedAt });
      }
      fields.push({ label: "Definition Hash", value: run.definitionHash });
      fields.push({ label: "Experiment Revision", value: run.experimentRevisionId });
      fields.push({ label: "Executions", value: String(run.statusSummary.total) });
      fields.push({ label: "Active Executions", value: String(run.statusSummary.active) });
      fields.push({ label: "Project ID", value: run.projectId });
      fields.push({ label: "Experiment ID", value: run.experimentId });
      return fields;
    },
    asset: () => {
      const asset = findAsset(snapshot, selection.objectId);
      if (!asset) {
        return emptyFields("asset", selection.objectId);
      }
      return [
        { label: "Asset", value: asset.name },
        { label: "Status", value: asset.status },
        { label: "Summary", value: asset.summary },
        { label: "Updated", value: asset.updatedAt },
        { label: "Size", value: `${asset.sizeBytes} bytes` },
      ];
    },
    workflow: () => {
      const workflow = findWorkflow(snapshot, selection.objectId);
      if (!workflow) {
        return emptyFields("workflow", selection.objectId);
      }
      return [
        { label: "Workflow", value: workflow.name },
        { label: "Project", value: workflow.projectId },
        { label: "Experiment", value: workflow.experimentId },
        { label: "Status", value: workflow.status },
        { label: "Summary", value: workflow.summary },
        { label: "Updated", value: workflow.updatedAt },
      ];
    },
    "workspace-file": () => {
      if (selection.objectType !== "workspace-file") {
        return emptyFields("workspace-file", selection.objectId);
      }
      return [
        { label: "File", value: selection.filePath },
        { label: "Kind", value: selection.fileKind },
      ];
    },
    task: () => {
      if (selection.objectType !== "task") {
        return emptyFields("task", selection.objectId);
      }
      return [
        { label: "Task", value: selection.taskId },
        { label: "Run", value: selection.runId },
      ];
    },
    knowledge: () => [
      { label: "Concept", value: selection.objectId || "(all)" },
      { label: "Kind", value: "OKF concept" },
    ],
  };

  const buildFields = lookupByType[selection.objectType];
  return buildFields();
};
