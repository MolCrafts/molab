/**
 * How an editor tab reads: its icon, its live label and, for a run, its
 * status. Labels come from the entity catalog when the entity is loaded and
 * fall back to the label stored at the tab's last sighting.
 */

import type { ComponentType, SVGProps } from "react";
import { compareSet } from "@/app/compare/useCompareSet";
import { entityMeta } from "@/app/entities/kinds";
import { listAllNavigationContributions } from "@/app/navigation/sections";
import { runLabel } from "@/app/runs/runTitle";
import type { WorkspaceSnapshot } from "@/app/types";
import type { EditorTab } from "./editorTabs";

type TabSnapshot = Pick<
  WorkspaceSnapshot,
  "projects" | "experiments" | "runs" | "workflows" | "assets"
> & {
  /** Knowledge documents by path, for their names (L10). */
  knowledge?: ReadonlyArray<{ relPath: string; name: string }>;
};

export interface EditorTabPresentation {
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Run state, drawn as the tab's leading glyph. */
  status?: string;
  /** Parent context for the tooltip and the mobile app bar. */
  context?: string;
}

const idOf = (tab: EditorTab): string => tab.key.slice(tab.key.indexOf(":") + 1);

const lastSegment = (path: string): string => path.split("/").filter(Boolean).pop() ?? path;

export const describeEditorTab = (tab: EditorTab, snapshot: TabSnapshot): EditorTabPresentation => {
  const id = idOf(tab);
  if (tab.kind === "section") {
    const section = listAllNavigationContributions().find((candidate) => candidate.id === id);
    // The Compare tab says how big the set is (L05): “Compare · 3 runs”.
    const pinned = id === "compare" ? compareSet.entries() : [];
    // Runs are counted as runs; a pinned project or experiment makes it “items”.
    const noun = pinned.every((item) => item.ref.kind === "run")
      ? pinned.length === 1
        ? "run"
        : "runs"
      : pinned.length === 1
        ? "item"
        : "items";
    return {
      label:
        pinned.length > 0
          ? `${section?.label ?? tab.label} · ${pinned.length} ${noun}`
          : (section?.label ?? tab.label),
      icon: section?.icon ?? entityMeta("project").icon,
    };
  }
  const icon = entityMeta(tab.kind).icon as EditorTabPresentation["icon"];
  switch (tab.kind) {
    case "project": {
      const project = snapshot.projects.find((candidate) => candidate.id === id);
      return { label: project?.name ?? tab.label, icon };
    }
    case "experiment": {
      const experiment = snapshot.experiments.find((candidate) => candidate.id === id);
      const project = experiment
        ? snapshot.projects.find((candidate) => candidate.id === experiment.projectId)
        : undefined;
      return { label: experiment?.name ?? tab.label, icon, context: project?.name };
    }
    case "run": {
      const run = snapshot.runs.find((candidate) => candidate.id === id);
      const experiment = run
        ? snapshot.experiments.find((candidate) => candidate.id === run.experimentId)
        : undefined;
      return {
        label: run ? runLabel(run) : tab.label,
        icon,
        status: run?.status,
        context: experiment?.name,
      };
    }
    case "task": {
      const [runId = "", taskId = tab.label] = id.split("/");
      const run = snapshot.runs.find((candidate) => candidate.id === runId);
      return { label: taskId, icon, context: run ? runLabel(run) : undefined };
    }
    case "workflow": {
      const workflow = snapshot.workflows.find((candidate) => candidate.id === id);
      return { label: workflow?.name ?? tab.label, icon };
    }
    case "asset": {
      const asset = snapshot.assets.find((candidate) => candidate.id === id);
      return { label: asset?.name ?? tab.label, icon };
    }
    case "knowledge":
      return {
        label: id
          ? (snapshot.knowledge?.find((doc) => doc.relPath === id)?.name ??
            lastSegment(id).replace(/\.(md|mdx|html)$/, ""))
          : entityMeta("knowledge").plural,
        icon,
      };
    case "workspace-file": {
      // The folder, not the path again: a root file's context would repeat its name (L07-8).
      const folder = id.includes("/") ? id.slice(0, id.lastIndexOf("/")) : "";
      return { label: lastSegment(id), icon, ...(folder ? { context: folder } : {}) };
    }
  }
};
