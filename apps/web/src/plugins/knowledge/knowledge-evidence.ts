import type { EntityCard } from "@/api/generated/models/EntityCard";
import { latestExecution } from "@/app/assets/AssetSections";
import type { WorkspaceRunRow } from "@/app/runs/types";
import type { AssetSummary, RendererSnapshot } from "@/app/types";
import { buildMolabRefIndex } from "@/lib/entity-linkify";
import { resolveMolabRef } from "@/lib/molab-ref";

export type EvidenceSource =
  | { kind: "none" }
  | { kind: "unresolved" | "missing-run"; message: string }
  | { kind: "missing-attempt"; run: WorkspaceRunRow; executionId: string | null; message: string }
  | { kind: "ready"; run: WorkspaceRunRow; executionId: string | null };

/** A source always keeps its experiment-qualified identity and recorded attempt.
 * The server's reported path can resolve a run absent from the shallow snapshot.
 * A bare legacy run id is never sufficient to pick a producing experiment. */
export const knowledgeEvidenceSource = (
  card: EntityCard,
  asset: AssetSummary | undefined,
  snapshot: RendererSnapshot,
  rows: readonly WorkspaceRunRow[],
): EvidenceSource => {
  if (card.missing) return { kind: "none" };
  let candidates: readonly WorkspaceRunRow[];
  if (card.kind === "run") {
    const resolved = card.ref
      ? resolveMolabRef(card.ref.split("#", 1)[0], buildMolabRefIndex(snapshot))
      : null;
    const indexed =
      resolved?.kind === "run" ? snapshot.runs.find((run) => run.ref === resolved.ref) : undefined;
    if (indexed) {
      candidates = rows.filter(
        (run) =>
          run.id === indexed.id &&
          run.projectId === indexed.projectId &&
          run.experimentId === indexed.experimentId,
      );
    } else if (card.relPath) {
      candidates = rows.filter((run) => run.id === card.id && run.path === card.relPath);
    } else {
      return {
        kind: "unresolved",
        message:
          "The referenced run's experiment is not loaded. Its bare run id cannot identify the source safely.",
      };
    }
  } else if (card.kind === "asset" && asset?.origin?.kind === "execution") {
    const origin = asset.origin;
    if (!origin.projectId || !origin.experimentId || !origin.runId) {
      return {
        kind: "unresolved",
        message:
          "The asset's producing project or experiment was not recorded in this response. Reload its source metadata to identify the run safely.",
      };
    }
    candidates = rows.filter(
      (run) =>
        run.id === origin.runId &&
        (run.projectId === origin.projectId || run.projectId === "") &&
        run.experimentId === origin.experimentId,
    );
  } else {
    return { kind: "none" };
  }
  if (candidates.length !== 1) {
    return {
      kind: "missing-run",
      message:
        candidates.length > 1
          ? "The source identity matches multiple runs; choose its producing scope before inspecting evidence."
          : "The qualified producing run is not in the loaded inventory.",
    };
  }
  const run = candidates[0];
  if (card.kind === "asset") {
    const executionId = asset?.origin?.executionId ?? null;
    if (
      !executionId ||
      !run.executions.some((execution) => execution.executionId === executionId)
    ) {
      return {
        kind: "missing-attempt",
        run,
        executionId,
        message: executionId
          ? `The recorded producing attempt ${executionId} is missing from this run. Its evidence cannot be replaced by a newer attempt.`
          : "The producing attempt was not recorded. Select the original attempt before inspecting its evidence.",
      };
    }
    return { kind: "ready", run, executionId };
  }
  return { kind: "ready", run, executionId: latestExecution(run)?.executionId ?? null };
};
