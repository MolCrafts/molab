// ─────────────────────────────────────────────────────────────────────────────
// Breadcrumb trail (L00) — where the active editor sits: project › experiment ›
// run › attempt for the hierarchy, section › entity for everything else. Each
// segment carries its kind so the row can draw the entity's icon, and every
// ancestor routes through the single ``entityPath`` URL builder. A section
// page (Runs, Settings…) has no trail: its editor tab already names it.
// ─────────────────────────────────────────────────────────────────────────────

import { entityMeta } from "@/app/entities/kinds";
import { entityPath, runPath } from "@/app/entities/paths";
import { listAllNavigationContributions } from "@/app/navigation/sections";
import { runLabel } from "@/app/runs/runTitle";
import type { BreadcrumbItem, LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { hostLabel } from "@/plugins/knowledge/hostLabel";

type TrailSnapshot = Pick<
  WorkspaceSnapshot,
  "projects" | "experiments" | "runs" | "workflows" | "assets"
>;

const item = (kind: BreadcrumbItem["kind"], label: string, to?: string): BreadcrumbItem =>
  to ? { kind, label, to } : { kind, label };

const runChain = (runId: string, snapshot: TrailSnapshot, linkRun: boolean): BreadcrumbItem[] => {
  const run = snapshot.runs.find((candidate) => candidate.id === runId);
  if (!run) return [item("run", runId)];
  const project = snapshot.projects.find((candidate) => candidate.id === run.projectId);
  const experiment = snapshot.experiments.find((candidate) => candidate.id === run.experimentId);
  const link = (kind: "project" | "experiment" | "run", id: string): string | undefined =>
    entityPath({ kind, id }, snapshot as WorkspaceSnapshot) ?? undefined;
  return [
    ...(project ? [item("project", project.name, link("project", project.id))] : []),
    ...(experiment ? [item("experiment", experiment.name, link("experiment", experiment.id))] : []),
    item("run", runLabel(run), linkRun ? link("run", run.id) : undefined),
  ];
};

/** The attempt the run page shows (its `?attempt=`, else the latest); it opens the Attempts view. */
const shownAttempt = (
  runId: string,
  attemptId: string | undefined,
  snapshot: TrailSnapshot,
): BreadcrumbItem[] => {
  const run = snapshot.runs.find((candidate) => candidate.id === runId);
  const shown =
    run?.executionHistory.find((execution) => execution.executionId === attemptId) ??
    run?.executionHistory.at(-1);
  if (!run || !shown) return [];
  return [
    item(
      "attempt",
      shown.executionId,
      runPath(run.projectId, run.experimentId, run.id, "executions", {
        attempt: attemptId ? shown.executionId : null,
      }),
    ),
  ];
};

export const buildTrail = (
  selection: Selection | null,
  leftPanelView: LeftPanelView,
  snapshot: TrailSnapshot,
): BreadcrumbItem[] => {
  if (!selection) return [];
  // The section an entity was opened from; before the registry activates (or
  // in a unit test) the kind's plural stands in, without a link.
  const section = listAllNavigationContributions().find(({ id }) => id === leftPanelView);
  const root = section
    ? item("section", section.breadcrumbLabel, section.route)
    : item("section", entityMeta(selection.objectType).plural);

  switch (selection.objectType) {
    case "project": {
      const project = snapshot.projects.find((p) => p.id === selection.objectId);
      return [item("project", project?.name ?? selection.objectId)];
    }
    case "experiment": {
      const experiment = snapshot.experiments.find((e) => e.id === selection.objectId);
      const project = experiment
        ? snapshot.projects.find((p) => p.id === experiment.projectId)
        : undefined;
      return [
        ...(project
          ? [
              item(
                "project",
                project.name,
                entityPath({ kind: "project", id: project.id }, snapshot as WorkspaceSnapshot) ??
                  undefined,
              ),
            ]
          : []),
        item("experiment", experiment?.name ?? selection.objectId),
      ];
    }
    case "run":
      return [
        ...runChain(selection.objectId, snapshot, true),
        ...shownAttempt(selection.objectId, selection.attemptId, snapshot),
      ];
    case "task":
      return [...runChain(selection.runId, snapshot, true), item("task", selection.taskId)];
    case "workflow": {
      const workflow = snapshot.workflows.find((w) => w.id === selection.workflowId);
      return [root, item("workflow", workflow?.name ?? selection.workflowId)];
    }
    case "asset": {
      const asset = snapshot.assets.find((a) => a.id === selection.objectId);
      return [root, item("asset", asset?.name ?? selection.objectId)];
    }
    case "knowledge": {
      if (!selection.objectId) return [];
      // The tab names the document; the trail says where it lives (L10), by name.
      const at = selection.objectId.lastIndexOf("/knowledges/");
      const hostPath = at >= 0 ? selection.objectId.slice(0, at) : "";
      return [
        root,
        ...hostLabel(snapshot, hostPath)
          .split(" › ")
          .map((part) => item("knowledge", part)),
      ];
    }
    case "workspace-file":
      return [
        root,
        item("workspace-file", selection.filePath.split("/").pop() ?? selection.filePath),
      ];
  }
};
