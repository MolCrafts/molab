import { describe, expect, it } from "@rstest/core";
import { buildEmptySnapshot } from "@/app/state/api";
import { fetchSlices, type SnapshotSlice, slicesForView } from "@/app/state/useWorkspaceState";
import type { WorkspaceSnapshot } from "@/app/types";

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

const deferred = <T>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
};

describe("slicesForView", () => {
  it("does not fetch the file tree on knowledge", () => {
    expect(slicesForView("knowledge")).toEqual(["workspaces"]);
  });

  it("loads the file tree only on Files", () => {
    expect(slicesForView("workspace")).toEqual(["workspaces", "workspaceTree"]);
  });

  it("loads projects for the projects explorer", () => {
    expect(slicesForView("projects")).toEqual(["workspaces", "projectsList"]);
    expect(slicesForView("compare")).toEqual(["workspaces", "projectsList"]);
  });

  it("keeps dashboard off the file tree", () => {
    expect(slicesForView("dashboard")).toEqual(["workspaces"]);
  });
});

describe("workspace bootstrap slice plan", () => {
  it("starts independent slices together and waits before loading projects", async () => {
    const gates = new Map<SnapshotSlice, Deferred<Partial<WorkspaceSnapshot>>>([
      ["workspaces", deferred()],
      ["workspaceTree", deferred()],
      ["projectsList", deferred()],
    ]);
    const starts: SnapshotSlice[] = [];
    const projectsStarted = deferred<void>();
    const workspace = {
      key: "local",
      label: "Local",
      path: "/workspace",
      root: "/workspace",
      active: true,
      isRemote: false,
      unreachable: false,
      needsAuth: false,
      readOnly: false,
    };

    const resultPromise = fetchSlices(
      buildEmptySnapshot(),
      ["workspaces", "projectsList", "workspaceTree"],
      undefined,
      async (snapshot, slice) => {
        starts.push(slice);
        if (slice === "projectsList") {
          expect(snapshot.workspaces).toEqual([workspace]);
          projectsStarted.resolve();
        }
        return gates.get(slice)?.promise ?? {};
      },
    );

    expect(starts).toEqual(["workspaces", "workspaceTree"]);

    gates.get("workspaces")?.resolve({ workspaces: [workspace] });
    gates.get("workspaceTree")?.resolve({ workspaceRoot: null });
    await projectsStarted.promise;

    expect(starts).toContain("projectsList");
    gates.get("projectsList")?.resolve({ projects: [] });

    await expect(resultPromise).resolves.toMatchObject({ workspaces: [workspace] });
  });

  it("loads assets only after the project patch is available", async () => {
    const starts: SnapshotSlice[] = [];
    const project = {
      id: "project-1",
      name: "Project 1",
      path: "projects/project-1",
      status: "active" as const,
      summary: "",
      updatedAt: "2026-08-31T00:00:00Z",
    };

    await fetchSlices(
      buildEmptySnapshot(),
      ["projectsList", "assets"],
      undefined,
      async (snapshot, slice) => {
        starts.push(slice);
        if (slice === "projectsList") return { projects: [project] };
        expect(snapshot.projects).toEqual([project]);
        return { assets: [] };
      },
    );

    expect(starts).toEqual(["projectsList", "assets"]);
  });
});
