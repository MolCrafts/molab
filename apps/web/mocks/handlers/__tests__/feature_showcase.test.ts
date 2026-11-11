import { describe, expect, it } from "@rstest/core";
import { getResponse } from "msw";

import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { lineagePaths } from "../../db/knowledge-lineage";
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

  it("serves all typed relations, actual backlinks and traceable sources from one fixture history", async () => {
    const graph = await getJson<KnowledgeGraphResponse>("/api/knowledge/graph");
    expect(new Set(graph.edges.map((edge) => edge.role))).toEqual(
      new Set([
        "derived_from",
        "cites",
        "supersedes",
        "supports",
        "contradicts",
        "records",
        "references",
      ]),
    );
    expect(graph.edges).toContainEqual({
      source: lineagePaths.decision,
      target: lineagePaths.oldDecision,
      role: "supersedes",
      kind: "document",
    });
    expect(graph.edges.some((edge) => edge.kind === "missing")).toBe(true);
    expect(graph.edges.some((edge) => edge.kind === "external")).toBe(true);
    const detail = await getJson<{
      body: string;
      cards: { relPath?: string; ref?: string; missing?: boolean }[];
    }>(`/api/knowledge/note?path=${encodeURIComponent(lineagePaths.decision)}`);
    expect(detail.body).toContain("[@supersedes Initial timestep policy]");
    expect(detail.cards.map((card) => card.relPath)).toEqual([
      lineagePaths.finding,
      lineagePaths.counterexample,
      lineagePaths.oldDecision,
    ]);
    expect(detail.cards.some((card) => card.ref?.includes("exp-001"))).toBe(false);
    const backlinks = await getJson<{ backlinks: { relPath: string }[] }>(
      `/api/knowledge/backlinks?path=${encodeURIComponent(lineagePaths.decision)}`,
    );
    expect(backlinks.backlinks.map((note) => note.relPath)).toEqual([lineagePaths.report]);
    const asset = await getJson<{ backlinks: { path: string; role: string }[] }>(
      "/api/knowledge/entity-backlinks?kind=asset&assetId=asset-nve-trajectory",
    );
    expect(asset.backlinks).toContainEqual(
      expect.objectContaining({ path: lineagePaths.finding, role: "derived_from" }),
    );
    const unrelated = await getJson<{ backlinks: unknown[] }>(
      "/api/knowledge/backlinks?path=not-a-document.md",
    );
    expect(unrelated.backlinks).toEqual([]);
  });

  it("derives edited links afresh and keeps a deleted target as a missing reference", async () => {
    const origin = "knowledges/lineage-test-origin.md";
    const child = "knowledges/lineage-test-child.md";
    const mutate = (method: string, path: string, body?: unknown) =>
      getResponse(
        handlers,
        new Request(`http://localhost${path}`, {
          method,
          headers: { "content-type": "application/json" },
          ...(body ? { body: JSON.stringify(body) } : {}),
        }),
      );
    try {
      await mutate("POST", "/api/knowledge/doc", { name: "Lineage test origin" });
      await mutate("POST", "/api/knowledge/doc", {
        name: "Lineage test child",
        body: `[@derived_from origin](${origin})`,
      });
      let graph = await getJson<KnowledgeGraphResponse>("/api/knowledge/graph");
      expect(graph.edges).toContainEqual({
        source: child,
        target: origin,
        role: "derived_from",
        kind: "document",
      });
      await mutate("PUT", `/api/knowledge/doc?path=${encodeURIComponent(child)}`, {
        body: `[@supersedes origin](${origin})`,
      });
      graph = await getJson<KnowledgeGraphResponse>("/api/knowledge/graph");
      expect(graph.edges.filter((edge) => edge.source === child).map((edge) => edge.role)).toEqual([
        "supersedes",
      ]);
      await mutate("DELETE", `/api/knowledge/doc?path=${encodeURIComponent(origin)}`);
      graph = await getJson<KnowledgeGraphResponse>("/api/knowledge/graph");
      expect(graph.edges).toContainEqual({
        source: child,
        target: origin,
        role: "supersedes",
        kind: "missing",
      });
    } finally {
      await mutate("DELETE", `/api/knowledge/doc?path=${encodeURIComponent(origin)}`);
      await mutate("DELETE", `/api/knowledge/doc?path=${encodeURIComponent(child)}`);
    }
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

it("keeps the saved mock document version after a working-copy edit", async () => {
  const path = lineagePaths.report;
  const url = `/api/history/document?document=${encodeURIComponent(path)}`;
  const history = await getJson<{ revisions: { commit: string }[] }>(url);
  expect(history.revisions).toHaveLength(1);
  const versionUrl = `${url}&commit=${history.revisions[0].commit}`;
  const before = await getJson<{ body: string; diff: string }>(versionUrl);
  const original = await getJson<{ body: string }>(
    `/api/knowledge/note?path=${encodeURIComponent(path)}`,
  );
  const response = await getResponse(
    handlers,
    new Request(`http://localhost/api/knowledge/doc?path=${encodeURIComponent(path)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: `${original.body}\nA new working-copy review.\n` }),
    }),
  );
  expect(response?.status).toBe(200);
  try {
    const after = await getJson<{ body: string; diff: string }>(versionUrl);
    expect(after.body).toBe(before.body);
    expect(after.diff).toContain("+A new working-copy review.");
  } finally {
    await getResponse(
      handlers,
      new Request(`http://localhost/api/knowledge/doc?path=${encodeURIComponent(path)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: original.body }),
      }),
    );
  }
});
