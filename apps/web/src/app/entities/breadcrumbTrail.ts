// ─────────────────────────────────────────────────────────────────────────────
// Breadcrumb trail — the ordered ancestor chain for the current selection,
// derived once from the entity graph. Replaces the ~140-line hand-rolled
// ``buildBreadcrumbs`` in useNavigationState; every trail link routes through
// the single ``entityPath`` URL builder. Lives in the shell, so EVERY view —
// including the dashboard landing pages that previously had no breadcrumb at
// all — gets a consistent trail.
// ─────────────────────────────────────────────────────────────────────────────

import { entityPath } from "@/app/entities/paths";
import { getNavigationContribution } from "@/app/navigation/sections";
import type { BreadcrumbItem, LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";

const crumb = (label: string, to?: string): BreadcrumbItem => (to ? { label, to } : { label });

export const buildTrail = (
  selection: Selection | null,
  leftPanelView: LeftPanelView,
  snapshot: WorkspaceSnapshot,
): BreadcrumbItem[] => {
  const contribution = getNavigationContribution(leftPanelView);
  const root = { label: contribution.breadcrumbLabel, to: contribution.route };
  const scope = snapshot.serveScope;
  const clipSectionRoot = Boolean(scope && scope.kind !== "workspace.root");

  const finish = (items: BreadcrumbItem[]): BreadcrumbItem[] => {
    if (!clipSectionRoot) return items;
    const rest = items.slice(1);
    return rest.length > 0 ? rest : [crumb(scope?.name || root.label)];
  };

  if (!selection) {
    // Section landing page — root only, not a link to itself.
    return finish([crumb(root.label)]);
  }

  const link = (kind: Selection["objectType"], id: string, runId?: string): string | undefined =>
    entityPath({ kind, id, runId }, snapshot) ?? undefined;

  switch (selection.objectType) {
    case "project": {
      const project = snapshot.projects.find((p) => p.id === selection.objectId);
      return finish([root, crumb(project?.name ?? selection.objectId)]);
    }
    case "experiment": {
      const experiment = snapshot.experiments.find((e) => e.id === selection.objectId);
      const project = experiment
        ? snapshot.projects.find((p) => p.id === experiment.projectId)
        : null;
      return finish([
        root,
        ...(project ? [crumb(project.name, link("project", project.id))] : []),
        crumb(experiment?.name ?? selection.objectId),
      ]);
    }
    case "run": {
      const run = snapshot.runs.find((r) => r.id === selection.objectId);
      const experiment = run ? snapshot.experiments.find((e) => e.id === run.experimentId) : null;
      const project = run ? snapshot.projects.find((p) => p.id === run.projectId) : null;
      return finish([
        root,
        ...(project ? [crumb(project.name, link("project", project.id))] : []),
        ...(experiment ? [crumb(experiment.name, link("experiment", experiment.id))] : []),
        crumb(run?.name ?? selection.objectId),
      ]);
    }
    case "task": {
      const run = snapshot.runs.find((r) => r.id === selection.runId);
      const experiment = run ? snapshot.experiments.find((e) => e.id === run.experimentId) : null;
      const project = run ? snapshot.projects.find((p) => p.id === run.projectId) : null;
      return finish([
        root,
        ...(project ? [crumb(project.name, link("project", project.id))] : []),
        ...(experiment ? [crumb(experiment.name, link("experiment", experiment.id))] : []),
        ...(run ? [crumb(run.name ?? run.id, link("run", run.id))] : []),
        crumb(selection.taskId),
      ]);
    }
    case "workflow": {
      const workflow = snapshot.workflows.find((w) => w.id === selection.workflowId);
      return finish([root, crumb(workflow?.name ?? selection.workflowId)]);
    }
    case "asset": {
      const asset = snapshot.assets.find((a) => a.id === selection.objectId);
      return finish([root, crumb(asset?.name ?? selection.objectId)]);
    }
    case "knowledge": {
      if (!selection.objectId) return finish([crumb(root.label)]);
      const name = selection.objectId.split("/").pop() ?? selection.objectId;
      return finish([root, crumb(name)]);
    }
    case "workspace-file":
      return finish([root, crumb(selection.filePath.split("/").pop() ?? selection.filePath)]);
  }
};
