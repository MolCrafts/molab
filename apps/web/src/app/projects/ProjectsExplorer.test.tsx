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

  it("shows a failed experiment load instead of an indefinite loading row", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [
      {
        id: "project-1",
        name: "Catalyst search",
        path: "projects/catalyst-search",
        status: "active",
        summary: "",
        updatedAt: "",
        experimentCount: 16,
        experimentsError: "Connection timed out",
      },
    ];
    const [node] = buildProjectNodes(
      snapshot,
      projectActions(() => undefined),
      "",
    );
    expect(node?.emptyChildLabel).toBe("Could not load experiments");
  });

  it("does not scan remote runs when the pointer passes over an experiment", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.projects = [
      { id: "p", name: "Project", path: "p", status: "active", summary: "", updatedAt: "" },
    ];
    snapshot.experiments = [
      {
        id: "e",
        name: "Experiment",
        path: "p/e",
        status: "active",
        summary: "",
        workflowFile: "",
        updatedAt: "",
        projectId: "p",
        parameterSpace: {},
        workflowSource: null,
      },
    ];
    const actions = projectActions(() => undefined);
    actions.pathContext.workspace = { label: "Arrhenius:/lab", path: null, isRemote: true };
    let scans = 0;
    let intents = 0;
    actions.onExpandProject = () => {
      scans += 1;
    };
    actions.onExpandExperiment = () => {
      scans += 1;
    };
    actions.onIntentExperiment = () => {
      intents += 1;
    };
    const [project] = buildProjectNodes(snapshot, actions, "");
    project?.children?.[0]?.onPrefetch?.();
    expect(scans).toBe(0);
    expect(intents).toBe(1);
    project?.children?.[0]?.onSelect?.();
    expect(scans).toBe(2);
  });
});
