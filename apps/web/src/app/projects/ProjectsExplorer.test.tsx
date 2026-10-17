import { describe, expect, it } from "@rstest/core";
import { buildEmptySnapshot } from "@/app/state/api";
import type { Selection } from "@/app/types";
import {
  buildProjectExpandPath,
  buildProjectNodes,
  type ProjectTreeActions,
} from "./ProjectsExplorer";

const projectActions = (onSelect: (selection: Selection) => void): ProjectTreeActions => ({
  onSelect,
  onCreateExperiment: () => undefined,
  onCreateRun: () => undefined,
  onDeleteProject: () => undefined,
  onDeleteExperiment: () => undefined,
  onOpenRunView: () => undefined,
  onCopyText: () => undefined,
  pathContext: { root: "/workspace", workspace: null },
  onRefresh: () => undefined,
  writeDeniedReason: "Viewer role cannot modify projects.",
  isProjectExpanded: () => false,
  workspaceKey: "lab-v3",
  workspaceLabel: "lab-v3",
});

describe("Projects explorer", () => {
  it("preserves shallow completeness and permission-gates project mutations", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [
      {
        id: "project-1",
        name: "Catalyst search",
        path: "projects/catalyst-search",
        status: "active",
        summary: "Screen catalyst candidates",
        updatedAt: "2026-08-30T12:00:00Z",
        experimentCount: 2,
      },
    ];
    let selected: Selection | null = null;
    const [node] = buildProjectNodes(
      snapshot,
      projectActions((next) => {
        selected = next;
      }),
      "",
    );

    expect(node?.selectionKey).toBe("lab-v3/project-1");
    expect(node?.emptyChildLabel).toBe("Loading…");
    expect(node?.actions?.find((action) => action.id === "delete")).toMatchObject({
      disabled: true,
      title: "Viewer role cannot modify projects.",
    });
    expect(typeof node?.onPrefetch).toBe("function");
    node?.onSelect?.();
    expect(selected).toEqual({ objectType: "project", objectId: "project-1" });
  });

  it("expands the active project without opening unrelated hierarchy", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [
      {
        id: "project-1",
        name: "Catalyst search",
        path: "projects/catalyst-search",
        status: "active",
        summary: "Screen catalyst candidates",
        updatedAt: "2026-08-30T12:00:00Z",
      },
    ];

    expect(buildProjectExpandPath(snapshot, "project-1", "")).toEqual(["project-1"]);
  });
});
