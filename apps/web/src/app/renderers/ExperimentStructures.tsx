import { useQueries, useQuery } from "@tanstack/react-query";
import { type JSX, Suspense, useMemo, useState } from "react";
import { EmptyState, InventoryCanvas, OverviewSurface } from "@/app/components/entity";
import {
  artifactContentQueryOptions,
  executionOutputsQueryOptions,
  runFileTextQueryOptions,
} from "@/app/state/entityQueries";
import type { RunSummary } from "@/app/types";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { isChemicalStructureName, structureRank } from "@/lib/structure-files";
import { cn } from "@/lib/utils";

interface ListedStructure {
  key: string;
  runName: string;
  runId: string;
  executionId: string;
  label: string;
  artifactId: string | null;
  path: string | null;
}

const latestExecutionId = (run: RunSummary): string | null =>
  run.executionHistory.at(-1)?.executionId ?? null;

/**
 * Every structure file from the latest attempt of each run, with one 2D formula
 * and 3D model open at a time.
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
    const rows: ListedStructure[] = [];
    attempts.forEach(({ run, executionId }, index) => {
      const body = outputs[index]?.data;
      if (!body) return;
      for (const artifact of body.artifacts ?? []) {
        if (!isChemicalStructureName(artifact.name)) continue;
        rows.push({
          key: `${run.id}:${artifact.id}`,
          runName: run.name || run.id,
          runId: run.id,
          executionId,
          label: artifact.name,
          artifactId: artifact.id,
          path: null,
        });
      }
      for (const file of body.unregistered ?? []) {
        if (!isChemicalStructureName(file.name)) continue;
        rows.push({
          key: `${run.id}:file:${file.relPath}`,
          runName: run.name || run.id,
          runId: run.id,
          executionId,
          label: file.name,
          artifactId: null,
          path: file.relPath,
        });
      }
    });
    rows.sort(
      (left, right) =>
        left.runName.localeCompare(right.runName) ||
        structureRank(left.label) - structureRank(right.label) ||
        left.label.localeCompare(right.label),
    );
    return rows;
  }, [attempts, outputs]);
  const [picked, setPicked] = useState<string | null>(null);
  const active = listed.find((row) => row.key === picked) ?? listed[0] ?? null;
  const run = active ? runs.find((item) => item.id === active.runId) : null;
  const artifactText = useQuery({
    ...artifactContentQueryOptions(
      run?.projectId ?? "",
      run?.experimentId ?? "",
      active?.runId ?? "",
      active?.executionId ?? "",
      active?.artifactId ?? "",
    ),
    enabled: Boolean(run && active?.artifactId),
  });
  const fileText = useQuery({
    ...runFileTextQueryOptions(
      run?.projectId ?? "",
      run?.experimentId ?? "",
      active?.runId ?? "",
      active?.executionId ?? "",
      active?.path ?? "",
    ),
    enabled: Boolean(run && active?.path),
  });
  const content = active?.artifactId ? (artifactText.data ?? null) : (fileText.data ?? null);
  const plugin = useMemo(() => {
    void generation;
    if (!active) return null;
    return filePreviewPluginRegistry.getPluginForFile(active.label, active.label);
  }, [generation, active]);
  const loading = attempts.length > 0 && outputs.some((query) => query.isPending);
  const Preview = plugin?.Component;

  return (
    <OverviewSurface surfaceClassName="flex min-h-0 flex-col overflow-hidden">
      <InventoryCanvas fill className="min-h-0 flex-1 gap-0 space-y-0">
        {listed.length === 0 ? (
          <div className="flex h-full items-center justify-center p-6">
            <EmptyState
              title={loading ? "Loading structures…" : "No structures yet"}
              description={
                loading
                  ? "Reading the latest attempt of each run."
                  : "PDB, XYZ, MOL2, and SDF files from a run show up here."
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
                      "flex w-full flex-col items-start rounded-none px-2 py-1.5 text-left",
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
              {Preview && content ? (
                <Suspense
                  fallback={
                    <p className="p-4 text-label text-muted-foreground">Loading structure…</p>
                  }
                >
                  <Preview
                    content={content}
                    name={active?.label ?? ""}
                    path={active?.label ?? ""}
                    folderId=""
                  />
                </Suspense>
              ) : (
                <p className="p-4 text-label text-muted-foreground">
                  {content === null ? "Loading structure…" : "No structure preview for this file."}
                </p>
              )}
            </div>
          </div>
        )}
      </InventoryCanvas>
    </OverviewSurface>
  );
};
