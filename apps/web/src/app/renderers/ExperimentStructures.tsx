import { useQueries, useQuery } from "@tanstack/react-query";
import { type JSX, Suspense, useMemo, useState } from "react";
import { EmptyState, InventoryCanvas, OverviewSurface } from "@/app/components/entity";
import { runLabel } from "@/app/runs/runTitle";
import {
  artifactBytesQueryOptions,
  artifactContentQueryOptions,
  executionOutputsQueryOptions,
} from "@/app/state/entityQueries";
import type { RunSummary } from "@/app/types";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { filePreviewPayload, filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { cn } from "@/lib/utils";

const readError = (error: unknown): string | null => {
  if (!error) return null;
  return error instanceof Error ? error.message : "Preview unavailable";
};

interface ListedAsset {
  key: string;
  runName: string;
  runId: string;
  executionId: string;
  label: string;
  artifactId: string;
}

const latestExecutionId = (run: RunSummary): string | null =>
  run.executionHistory.at(-1)?.executionId ?? null;

/**
 * Every asset the latest attempt of each run registered. The host does not
 * choose a format: a file-preview plugin claims the file, or the row has no preview.
 */
export const ExperimentStructures = ({ runs }: { runs: readonly RunSummary[] }): JSX.Element => {
  const generation = useContributionGeneration();
  const attempts = useMemo(
    () =>
      runs.flatMap((run) => {
        const executionId = latestExecutionId(run);
        return executionId ? [{ run, executionId }] : [];
      }),
    [runs],
  );
  const outputs = useQueries({
    queries: attempts.map(({ run, executionId }) =>
      executionOutputsQueryOptions(run.projectId, run.experimentId, run.id, executionId),
    ),
  });
  const listed = useMemo(() => {
    const rows: ListedAsset[] = [];
    attempts.forEach(({ run, executionId }, index) => {
      const body = outputs[index]?.data;
      if (!body) return;
      for (const asset of body.assets ?? []) {
        rows.push({
          key: `${run.id}:${asset.id}`,
          runName: runLabel(run),
          runId: run.id,
          executionId,
          label: asset.title,
          artifactId: asset.id,
        });
      }
    });
    rows.sort(
      (left, right) =>
        left.runName.localeCompare(right.runName) || left.label.localeCompare(right.label),
    );
    return rows;
  }, [attempts, outputs]);
  const [picked, setPicked] = useState<string | null>(null);
  const active = listed.find((row) => row.key === picked) ?? listed[0] ?? null;
  const run = active ? runs.find((item) => item.id === active.runId) : null;
  const plugin = useMemo(() => {
    void generation;
    if (!active) return null;
    return filePreviewPluginRegistry.getPluginForFile(active.label, active.label);
  }, [generation, active]);
  const payload =
    plugin && active
      ? filePreviewPayload(plugin, { name: active.label, path: active.label })
      : "text";
  const wantsBytes = Boolean(plugin && payload === "bytes");
  const projectId = run?.projectId ?? "";
  const experimentId = run?.experimentId ?? "";
  const runId = active?.runId ?? "";
  const executionId = active?.executionId ?? "";
  const artifactId = active?.artifactId ?? "";
  const artifactText = useQuery({
    // `whole` is the plugin's request. The log cap splits a structure mid-record.
    ...artifactContentQueryOptions(
      projectId,
      experimentId,
      runId,
      executionId,
      artifactId,
      plugin?.whole === true,
    ),
    enabled: Boolean(run && active && plugin && !wantsBytes),
  });
  const artifactBytes = useQuery({
    ...artifactBytesQueryOptions(projectId, experimentId, runId, executionId, artifactId),
    enabled: Boolean(run && active && wantsBytes),
  });
  const content = artifactText.data ?? null;
  const bytes = artifactBytes.data ?? null;
  const previewError = readError(wantsBytes ? artifactBytes.error : artifactText.error);
  const loading = attempts.length > 0 && outputs.some((query) => query.isPending);
  const Preview = plugin?.Component;
  const ready = wantsBytes ? bytes !== null : content !== null;

  return (
    <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
      <InventoryCanvas fill className="min-h-0 flex-1 gap-0 space-y-0">
        {listed.length === 0 ? (
          <div className="flex h-full items-center justify-center p-6">
            <EmptyState
              title={loading ? "Loading assets…" : "No assets yet"}
              description={
                loading
                  ? "Reading the latest attempt of each run."
                  : "Assets a run registers show up here. A plugin previews the formats it claims."
              }
            />
          </div>
        ) : (
          <div className="grid h-full min-h-0 grid-cols-[minmax(220px,28%)_1fr]">
            <ul className="min-h-0 overflow-auto border-r border-border p-2">
              {listed.map((row) => (
                <li key={row.key}>
                  <button
                    type="button"
                    onClick={() => setPicked(row.key)}
                    className={cn(
                      "flex w-full flex-col items-start rounded-none px-2 py-row-pad text-left",
                      row.key === active?.key
                        ? "bg-accent-muted text-accent-muted-foreground"
                        : "text-muted-foreground hover:bg-interactive hover:text-foreground",
                    )}
                  >
                    <span className="truncate font-mono text-micro">{row.label}</span>
                    <span className="truncate text-micro text-muted-foreground">{row.runName}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="min-h-0 overflow-hidden">
              {previewError ? (
                <p className="p-4 text-label text-destructive">{previewError}</p>
              ) : Preview && ready && active ? (
                <Suspense
                  fallback={<p className="p-4 text-label text-muted-foreground">Loading…</p>}
                >
                  <Preview
                    key={active.key}
                    content={content ?? ""}
                    bytes={wantsBytes ? (bytes ?? undefined) : undefined}
                    name={active.label}
                    path={active.label}
                    folderId=""
                    assetId={active.artifactId}
                  />
                </Suspense>
              ) : (
                <p className="p-4 text-label text-muted-foreground">
                  {plugin ? "Loading…" : "No preview plugin claims this asset."}
                </p>
              )}
            </div>
          </div>
        )}
      </InventoryCanvas>
    </OverviewSurface>
  );
};
