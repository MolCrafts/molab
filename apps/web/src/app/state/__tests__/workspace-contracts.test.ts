import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient } from "@tanstack/react-query";
import { projectsWsApi, workspaceApi } from "@/api";
import { workspacesApi } from "@/api/workspaces";
import { workspaceRunKey } from "@/app/runs/jobsTable";
import { workspaceRunsQueryOptions } from "@/app/runs/useWorkspaceRuns";
import { buildEmptySnapshot } from "../api";
import { runKeys } from "../entityQueries";
import {
  fetchSlices,
  servedWorkspacesQueryOptions,
  workspaceCatalogQueryOptions,
} from "../useWorkspaceState";
import { emitWorkspaceSwitching, getWorkspaceQueryScope } from "../workspaceSwitchEvents";

rs.mock("@/api/workspaces", () => ({ workspacesApi: { listWorkspaces: rs.fn() } }));
rs.mock("@/api", () => ({
  workspacesApi: { listWorkspaces: () => workspacesApi.listWorkspaces() },
  projectsApi: { listProjects: rs.fn().mockResolvedValue([]) },
  projectsWsApi: { listProjects: rs.fn().mockResolvedValue([]) },
  workspaceApi: { getServeScope: rs.fn().mockResolvedValue({ kind: "workspace.root" }) },
}));
afterEach(() => {
  rs.restoreAllMocks();
});

describe("workspace read contracts", () => {
  it("reports a failed required slice instead of publishing an empty success", async () => {
    const error = new Error("permission denied");
    await expect(
      fetchSlices(buildEmptySnapshot(), ["projectsList"], undefined, async () => {
        throw error;
      }),
    ).rejects.toBe(error);
  });

  it("keeps cloned runs independently selectable", () => {
    const first = { workspaceKey: "a", projectId: "p", experimentId: "e", id: "r" };
    const second = { ...first, workspaceKey: "b" };
    const a = workspaceRunKey(first as Parameters<typeof workspaceRunKey>[0]);
    const b = workspaceRunKey(second as Parameters<typeof workspaceRunKey>[0]);
    expect(a).not.toBe(b);
    expect(new Set([a]).has(b)).toBe(false);
  });

  it("never reuses cached artifact bytes after a connection switch", () => {
    const original = globalThis.window;
    rs.stubGlobal("window", new EventTarget());
    const client = new QueryClient();
    try {
      const before = runKeys.artifactContent("p", "e", "r", "e01", "a");
      client.setQueryData(before, "first workspace");
      const scope = getWorkspaceQueryScope();
      emitWorkspaceSwitching({ activeDescriptor: "second" });
      expect(getWorkspaceQueryScope()).not.toBe(scope);
      const after = runKeys.artifactContent("p", "e", "r", "e01", "a");
      expect(client.getQueryData(after)).toBeUndefined();
    } finally {
      client.clear();
      rs.stubGlobal("window", original);
    }
  });

  it("does not turn a failed served-set lookup into an active-workspace fallback", async () => {
    const error = new Error("server unavailable");
    rs.mocked(workspacesApi.listWorkspaces).mockRejectedValue(error);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    try {
      await expect(client.fetchQuery(workspaceRunsQueryOptions())).rejects.toBe(error);
    } finally {
      client.clear();
    }
  });
});

it("waits for the refreshed served set before loading its projects", async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const scope = "dependency-refresh";
  const rows = (keys: string[]) =>
    keys.map((key) => ({
      key,
      label: key,
      active: key === "a",
      isRemote: false,
      path: null,
      unreachable: false,
    }));
  client.setQueryData(servedWorkspacesQueryOptions(scope).queryKey, rows(["a", "deleted"]));
  await client.invalidateQueries({
    queryKey: servedWorkspacesQueryOptions(scope).queryKey,
    refetchType: "none",
  });
  let release!: (value: unknown) => void;
  rs.mocked(workspacesApi.listWorkspaces).mockImplementation(
    () =>
      new Promise((resolve) => {
        release = resolve as typeof release;
      }),
  );
  rs.mocked(projectsWsApi.listProjects).mockReset().mockResolvedValue([]);
  rs.mocked(workspaceApi.getServeScope)
    .mockReset()
    .mockResolvedValue({ kind: "workspace.root" } as Awaited<
      ReturnType<typeof workspaceApi.getServeScope>
    >);
  const pending = client.fetchQuery(workspaceCatalogQueryOptions(client, scope));
  expect(projectsWsApi.listProjects).not.toHaveBeenCalled();
  release(rows(["a", "new"]));
  try {
    await pending;
    expect(projectsWsApi.listProjects).toHaveBeenCalledWith("a");
    expect(projectsWsApi.listProjects).toHaveBeenCalledWith("new");
    expect(projectsWsApi.listProjects).not.toHaveBeenCalledWith("deleted");
  } finally {
    client.clear();
  }
});
