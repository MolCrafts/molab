import { describe, expect, it } from "@rstest/core";
import { getResponse } from "msw";

import { handlers } from "../index";

Reflect.set(globalThis, "location", new URL("http://localhost/"));

const getJson = async <T>(path: string): Promise<T> => {
  const response = await getResponse(handlers, new Request(`http://localhost${path}`));
  expect(response?.status).toBe(200);
  return (await response?.json()) as T;
};

describe("feature showcase mock", () => {
  it("keeps the entity tree and workspace runs dashboard on one fixture set", async () => {
    const experiments = await getJson<Array<{ id: string; runCount: number }>>(
      "/api/projects/protein-folding/experiments",
    );
    const alphaFoldRuns = await getJson<Array<{ id: string; status: string }>>(
      "/api/projects/protein-folding/experiments/exp-001/runs",
    );
    const workspaceRuns = await getJson<{
      total: number;
      stats: {
        totalRuns: number;
        totalExecutions: number;
        activeExecutions: number;
        byStatus: Record<string, number>;
      };
      runs: Array<{
        id: string;
        name: string;
        statusSummary: { byStatus: Record<string, number>; notStarted: boolean; active: number };
        executions: Array<{ status: string; createdAt: string; executionId: string }>;
      }>;
    }>("/api/workspace/runs");

    const presentationStatus = (row: (typeof workspaceRuns.runs)[number]): string => {
      const counts = row.statusSummary.byStatus;
      if ((counts.running ?? 0) > 0 || (counts.finalizing ?? 0) > 0) return "running";
      if ((counts.queued ?? 0) > 0) return "pending";
      const latest = [...row.executions].sort(
        (left, right) =>
          right.createdAt.localeCompare(left.createdAt) ||
          right.executionId.localeCompare(left.executionId),
      )[0];
      if (latest?.status === "interrupted") return "failed";
      return latest?.status ?? "pending";
    };

    expect(experiments.find((row) => row.id === "exp-001")?.runCount).toBe(alphaFoldRuns.length);
    expect(workspaceRuns.runs.some((row) => row.id === "run-001")).toBe(true);
    expect(workspaceRuns.stats.byStatus).toEqual(expect.any(Object));
    expect(workspaceRuns.stats.totalRuns).toBe(workspaceRuns.total);
    expect(new Set(workspaceRuns.runs.map(presentationStatus))).toEqual(
      new Set(["succeeded", "running", "failed", "cancelled", "pending"]),
    );
  });

  it("populates the cross-feature navigation surfaces", async () => {
    const workspaces = await getJson<unknown[]>("/api/workspaces");
    const knowledge = await getJson<{ total: number }>("/api/knowledge");

    expect(workspaces.length).toBeGreaterThan(0);
    expect(knowledge.total).toBeGreaterThan(0);
  });

  it("exposes renderable MolPlot and MolVis products on the showcase run", async () => {
    const files = await getJson<{
      nodes: Array<{ relPath: string; children?: Array<{ relPath: string }> }>;
    }>(
      "/api/projects/protein-folding/experiments/exp-001/runs/run-001/executions/exec-run-001-01/files",
    );
    const paths = files.nodes.flatMap((node) => [
      node.relPath,
      ...(node.children ?? []).flatMap((child) => [
        child.relPath,
        ...((child as { children?: Array<{ relPath: string }> }).children ?? []).map(
          (n) => n.relPath,
        ),
      ]),
    ]);

    expect(paths).toContain("out/observables/energy.mlp.vl.json");
    expect(paths).toContain("out/trajectory.xyz");

    const plot = await getJson<{ content: string }>(
      "/api/projects/protein-folding/experiments/exp-001/runs/run-001/executions/exec-run-001-01/file/text?path=out%2Fobservables%2Fenergy.mlp.vl.json",
    );
    const plotSpec = JSON.parse(plot.content) as { title?: string };
    expect(plotSpec.title).toBe("Potential energy convergence");

    const trajectory = await getJson<{ content: string }>(
      "/api/projects/protein-folding/experiments/exp-001/runs/run-001/executions/exec-run-001-01/file/text?path=out%2Ftrajectory.xyz",
    );
    expect(trajectory.content).toContain("frame 1");
  });

  it("creates, moves and deletes a document by hostPath", async () => {
    const created = await getResponse(
      handlers,
      new Request("http://localhost/api/knowledge/doc", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: "X", hostPath: "" }),
      }),
    );
    expect(created?.status).toBe(201);

    const listed = await getJson<{
      notes: Array<{ relPath: string; hostPath: string }>;
    }>("/api/knowledge");
    expect(listed.notes).toContainEqual(
      expect.objectContaining({ relPath: "knowledges/x.md", hostPath: "" }),
    );

    const moved = await getResponse(
      handlers,
      new Request("http://localhost/api/knowledge/doc?path=knowledges%2Fx.md", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ hostPath: "projects/p" }),
      }),
    );
    expect(moved?.status).toBe(200);
    const afterMove = await getJson<{
      notes: Array<{ relPath: string; hostPath: string }>;
    }>("/api/knowledge");
    expect(afterMove.notes).toContainEqual(
      expect.objectContaining({
        relPath: "projects/p/knowledges/x.md",
        hostPath: "projects/p",
      }),
    );

    const removed = await getResponse(
      handlers,
      new Request("http://localhost/api/knowledge/doc?path=projects%2Fp%2Fknowledges%2Fx.md", {
        method: "DELETE",
      }),
    );
    expect(removed?.status).toBe(200);
    const afterDelete = await getJson<{ notes: Array<{ relPath: string }> }>("/api/knowledge");
    expect(
      afterDelete.notes.some(
        (row) => row.relPath.endsWith("/x.md") || row.relPath === "knowledges/x.md",
      ),
    ).toBe(false);
  });
});
