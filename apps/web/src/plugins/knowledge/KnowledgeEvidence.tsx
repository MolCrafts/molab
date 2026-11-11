/** Evidence stays beside the claim; bytes and plots use the existing asset/run hosts. */
import type { RunAttempt } from "@molcrafts/molab-plugin";
import { RunViewHostProvider } from "@molcrafts/molab-plugin/ui";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import { AssetContent } from "@/app/assets/AssetContent";
import { latestExecution, RunDetails } from "@/app/assets/AssetSections";
import { kindOfAsset } from "@/app/assets/assetKinds";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { usePreview } from "@/app/preview/PreviewContext";
import { useRunViewHost, useRunViews } from "@/app/renderers/run/useRunViews";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { mapAssets } from "@/app/state/api";
import { assetDetailQueryOptions } from "@/app/state/entityQueries";
import type { RendererSnapshot } from "@/app/types";
import { formatBytes } from "@/lib/format-bytes";
import { knowledgeEvidenceSource } from "./knowledge-evidence";

function EvidencePlots({ run, executionId }: { run: WorkspaceRunRow; executionId: string }) {
  const preview = usePreview();
  const base = useMemo(
    (): RunAttempt => ({
      projectId: run.projectId,
      experimentId: run.experimentId,
      runId: run.id,
      executionId,
      status: run.executions.find((item) => item.executionId === executionId)?.status ?? "pending",
      isLatest: latestExecution(run)?.executionId === executionId,
      isRunResult:
        [...run.executions].reverse().find((item) => item.status === "succeeded")?.executionId ===
        executionId,
      dir: null,
    }),
    [run, executionId],
  );
  const views = useRunViews(base);
  const attempt = useMemo(() => ({ ...base, dir: views.dir }), [base, views.dir]);
  const links = useMemo(
    () => ({
      openFile: (path: string) => {
        if (views.dir)
          preview.open({ kind: "file", filePath: `${views.dir}/${path}`, fileKind: "text" });
      },
      openLogs: () =>
        preview.open({
          kind: "attempt",
          projectId: run.projectId,
          experimentId: run.experimentId,
          runId: run.id,
          executionId,
          workspaceKey: run.workspaceKey,
        }),
    }),
    [preview, views.dir, run, executionId],
  );
  const host = useRunViewHost(attempt, links);
  const plot = views.tabs.find((tab) => tab.contribution.id === "molplot");
  const Component = plot?.contribution.Component;
  return views.error ? (
    <div role="alert">
      <p className="tw-red">Could not read this attempt's files: {views.error}</p>
      <button type="button" className="tw-button" onClick={views.refetch}>
        Retry attempt files
      </button>
    </div>
  ) : views.loading ? (
    <p className="tw-muted">Loading attempt files…</p>
  ) : Component && plot && host ? (
    <div className="tw-evidence-plot">
      <RunViewHostProvider value={host}>
        <Component attempt={attempt} files={plot.files} />
      </RunViewHostProvider>
    </div>
  ) : (
    <p className="tw-muted">This attempt has no files supported by MolPlot.</p>
  );
}

export function KnowledgeEvidence({
  card,
  projectId,
  snapshot,
  onClose,
}: {
  card: EntityCard;
  projectId: string;
  snapshot: RendererSnapshot;
  onClose: () => void;
}) {
  const preview = usePreview();
  const [plots, setPlots] = useState(false);
  const detail = useQuery({
    ...assetDetailQueryOptions(projectId, card.id),
    enabled: card.kind === "asset" && !card.missing,
  });
  const asset = useMemo(
    () =>
      detail.data
        ? mapAssets([detail.data], projectId)[0]
        : snapshot.assets.find((item) => item.id === card.id),
    [detail.data, projectId, snapshot.assets, card.id],
  );
  const needsRun = !card.missing && (card.kind === "run" || asset?.origin?.kind === "execution");
  const inventory = useScopeRuns({}, needsRun);
  const source = useMemo(
    () => knowledgeEvidenceSource(card, asset, snapshot, inventory.rows),
    [card, asset, snapshot, inventory.rows],
  );
  const run = source.kind === "ready" || source.kind === "missing-attempt" ? source.run : null;
  const executionId = source.kind === "ready" ? source.executionId : null;
  const openRun = () => {
    if (!run) return;
    const scope = {
      projectId: run.projectId,
      experimentId: run.experimentId,
      runId: run.id,
      workspaceKey: run.workspaceKey,
    };
    preview.open(
      executionId ? { kind: "attempt", ...scope, executionId } : { kind: "run", ...scope },
    );
  };
  return (
    <section className="tw-evidence" aria-label="Evidence preview">
      <div className="tw-row">
        <h3 className="tw-eyebrow">Evidence · {card.kind}</h3>
        <span className="tw-grow" />
        <button type="button" className="tw-close" aria-label="Close evidence" onClick={onClose}>
          ✕
        </button>
      </div>
      <strong>{card.title}</strong>
      {card.ref && <p className="tw-path">{card.ref}</p>}
      {card.missing ? <p className="tw-amber">The referenced source is missing.</p> : null}
      {detail.error && (
        <p className="tw-red" role="alert">
          {detail.error instanceof Error ? detail.error.message : "Could not read source"}
        </p>
      )}
      {card.kind === "asset" && detail.isFetching && !asset && (
        <p className="tw-muted">Loading source…</p>
      )}
      {asset && card.kind === "asset" && (
        <>
          <div className="tw-kv">
            <span>Recorded</span>
            <span>{asset.updatedAt}</span>
          </div>
          <div className="tw-kv">
            <span>Format / size</span>
            <span>
              {asset.mediaType || kindOfAsset(asset)} ·{" "}
              {asset.sizeBytes === null ? "unknown size" : formatBytes(asset.sizeBytes)}
            </span>
          </div>
          {asset.origin?.uri && <p className="tw-path">Imported from {asset.origin.uri}</p>}
          <div className="tw-evidence-content">
            <AssetContent asset={asset} kind={kindOfAsset(asset)} mode="thumb" />
          </div>
          {snapshot.assets.some((item) => item.id === asset.id) && (
            <button
              type="button"
              className="tw-link"
              onClick={() => preview.open({ kind: "asset", assetId: asset.id })}
            >
              Open asset tab ↗
            </button>
          )}
        </>
      )}
      {needsRun && inventory.query.isPending && <p className="tw-muted">Loading producing run…</p>}
      {inventory.query.error && (
        <p className="tw-red" role="alert">
          Could not load producing run.
          <button type="button" className="tw-link" onClick={() => void inventory.query.refetch()}>
            Retry run inventory
          </button>
        </p>
      )}
      {source.kind === "ready" && run && (
        <>
          <button type="button" className="tw-link" onClick={openRun}>
            Open {run.title || run.name} · {executionId ?? "not started"} ↗
          </button>
          <RunDetails run={run} executionId={executionId} task={asset?.origin?.task} />
          {executionId && (
            <button
              type="button"
              className="tw-button"
              aria-expanded={plots}
              onClick={() => setPlots((value) => !value)}
            >
              {plots ? "Hide MolPlot" : "Preview MolPlot"}
            </button>
          )}
          {plots && executionId && <EvidencePlots run={run} executionId={executionId} />}
        </>
      )}
      {needsRun &&
        !inventory.query.isPending &&
        !inventory.query.error &&
        source.kind !== "none" &&
        source.kind !== "ready" && (
          <p className="tw-amber" role="status">
            {source.message}
            {source.kind === "missing-run" && inventory.truncated
              ? " (Inventory limit reached.)"
              : ""}
          </p>
        )}
      {card.kind !== "asset" && card.kind !== "run" && card.detail && <p>{card.detail}</p>}
    </section>
  );
}
