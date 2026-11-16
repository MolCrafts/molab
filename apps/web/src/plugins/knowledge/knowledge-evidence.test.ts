import { describe, expect, it } from "@rstest/core";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { AssetSummary, RendererSnapshot, RunSummary } from "@/app/types";
import { knowledgeEvidenceSource } from "./knowledge-evidence";

const card: EntityCard = { kind: "run", id: "r1", title: "Run", ref: "molab:experiment/b/run/r1" };
const row = (experimentId: string, attempts = ["e01", "e02"]): WorkspaceRunRow =>
  ({
    id: "r1",
    projectId: "p",
    experimentId,
    name: "Run",
    path: `projects/p/experiments/${experimentId}/runs/r1`,
    executions: attempts.map((executionId, index) => ({
      executionId,
      createdAt: `2026-01-0${index + 1}`,
      status: "succeeded",
    })),
  }) as WorkspaceRunRow;
const snapshot = (runs: Partial<RunSummary>[] = []): RendererSnapshot =>
  ({
    projects: [],
    experiments: [],
    assets: [],
    runs,
  }) as unknown as RendererSnapshot;
const known = snapshot([
  { id: "r1", projectId: "p", experimentId: "b", ref: card.ref ?? undefined },
]);
const asset = (
  experimentId: string | null = "b",
  executionId: string | null = "e01",
): AssetSummary =>
  ({
    id: "asset",
    name: "Evidence",
    projectId: "owner",
    origin: {
      kind: "execution",
      projectId: "p",
      experimentId,
      runId: "r1",
      executionId,
      task: null,
      uri: null,
    },
  }) as AssetSummary;
const assetCard: EntityCard = { kind: "asset", id: "asset", title: "Evidence" };

describe("knowledge evidence source identity", () => {
  it("resolves a canonical run ref against snapshot identity rather than the first repeated run id", () => {
    const a = row("a");
    const b = row("b");
    expect(knowledgeEvidenceSource(card, undefined, known, [a, b])).toMatchObject({
      kind: "ready",
      run: b,
      executionId: "e02",
    });
    expect(knowledgeEvidenceSource(card, undefined, known, [a])).toMatchObject({
      kind: "missing-run",
    });
  });

  it("uses a literal server-reported path when the run is absent from the shallow snapshot", () => {
    const a = row("a");
    const b = row("b");
    expect(
      knowledgeEvidenceSource({ ...card, relPath: b.path }, undefined, snapshot(), [a, b]),
    ).toMatchObject({ kind: "ready", run: b });
    expect(knowledgeEvidenceSource(card, undefined, snapshot(), [b])).toMatchObject({
      kind: "unresolved",
    });
  });

  it("keeps the immutable producing attempt and origin scope separate from asset ownership", () => {
    const a = row("a");
    const b = row("b");
    expect(knowledgeEvidenceSource(assetCard, asset(), known, [a, b])).toMatchObject({
      kind: "ready",
      run: b,
      executionId: "e01",
    });
    expect(knowledgeEvidenceSource(assetCard, asset(), known, [a])).toMatchObject({
      kind: "missing-run",
    });
    expect(knowledgeEvidenceSource(assetCard, asset(null), known, [b])).toMatchObject({
      kind: "unresolved",
    });
    expect(
      knowledgeEvidenceSource(
        assetCard,
        {
          ...asset(),
          origin: {
            kind: "execution",
            projectId: "other",
            experimentId: "b",
            runId: "r1",
            executionId: "e01",
            task: null,
            uri: null,
          },
        },
        known,
        [b],
      ),
    ).toMatchObject({ kind: "missing-run" });
  });

  it("never substitutes the latest attempt when the recorded attempt is missing or unrecorded", () => {
    const b = row("b", ["e02"]);
    expect(knowledgeEvidenceSource(assetCard, asset(), known, [b])).toMatchObject({
      kind: "missing-attempt",
      executionId: "e01",
    });
    expect(knowledgeEvidenceSource(assetCard, asset("b", null), known, [b])).toMatchObject({
      kind: "missing-attempt",
      executionId: null,
    });
  });

  it("can match an experiment served without its ancestor project while rejecting ambiguous inventory", () => {
    const b = { ...row("b"), projectId: "" };
    expect(knowledgeEvidenceSource(assetCard, asset(), known, [b])).toMatchObject({
      kind: "ready",
      run: b,
    });
    expect(knowledgeEvidenceSource(assetCard, asset(), known, [b, b])).toMatchObject({
      kind: "missing-run",
    });
  });

  it("does not infer producing runs for imports or explicitly missing sources", () => {
    expect(
      knowledgeEvidenceSource(
        assetCard,
        {
          ...asset(),
          origin: { kind: "import", runId: null, executionId: null, task: null, uri: "file.csv" },
        },
        known,
        [row("b")],
      ),
    ).toEqual({ kind: "none" });
    expect(
      knowledgeEvidenceSource({ ...card, missing: true }, undefined, known, [row("b")]),
    ).toEqual({ kind: "none" });
  });
});
