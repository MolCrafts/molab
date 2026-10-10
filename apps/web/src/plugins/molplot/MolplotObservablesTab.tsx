/**
 * molplot plugin tab — data-driven when MolRec / plot artifacts are present.
 *
 * Vega-Lite artifacts (``*.mlp.vl.json``) render directly through MolPlot.
 * MolRec Zarr ``observables/`` arrays are not opened in-browser yet.
 */

import type { VegaLiteSpec } from "@molcrafts/molplot";
import { BarChart3, FileText } from "lucide-react";
import type { JSX } from "react";
import { useEffect, useMemo, useState } from "react";
import { runsApi } from "@/api";
import { EmptyState } from "@/app/components/entity";
import type { RendererProps } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import type { DiscoveredFile } from "@/plugins/types";
import { molplotDisplayName } from "./display-name";
import { MolplotRawChart } from "./MolplotRawChart";
export const MolplotObservablesTab = ({
  selection,
  snapshot,
  discoveredFiles,
  executionId,
}: RendererProps & { discoveredFiles: DiscoveredFile[] }): JSX.Element => {
  const [selected, setSelected] = useState(discoveredFiles[0]?.relPath ?? "");
  const [spec, setSpec] = useState<VegaLiteSpec | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = useMemo(
    () => snapshot.runs.find((item) => item.id === selection.objectId) ?? null,
    [selection.objectId, snapshot.runs],
  );

  const file = discoveredFiles.find((f) => f.relPath === selected) ?? discoveredFiles[0];

  useEffect(() => {
    if (!file && discoveredFiles[0]) setSelected(discoveredFiles[0].relPath);
  }, [file, discoveredFiles]);

  useEffect(() => {
    if (!file || !run || !executionId) return;
    let cancelled = false;
    setSpec(null);
    setError(null);
    setLoading(false);

    if (!file.name.toLowerCase().endsWith(".mlp.vl.json")) {
      setError(
        "Not a molplot Vega-Lite artifact (expected *.mlp.vl.json). Host metrics curves use *.mlp.jsonl via the Metrics tab.",
      );
      return;
    }

    setLoading(true);
    runsApi
      .getRunFileText(run.projectId, run.experimentId, run.id, executionId, file.relPath)
      .then((response) => {
        if (cancelled) return;
        const parsed: unknown = JSON.parse(response.content);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          throw new Error("The plot artifact is not a Vega-Lite object.");
        }
        setSpec(parsed as VegaLiteSpec);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Failed to load plot artifact");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [executionId, file, run]);

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="flex w-56 flex-none flex-col border-r border-border bg-surface-subtle">
        <div className="flex h-toolbar-compact items-center gap-2 border-b border-border px-3">
          <BarChart3 className="size-icon text-accent" aria-hidden />
          <span className="text-label font-medium text-foreground">MolPlot</span>
          <span className="ml-auto font-mono text-micro text-muted-foreground">
            {discoveredFiles.length}
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-1">
          {discoveredFiles.map((candidate) => (
            <WorkbenchAction
              kind="ghost"
              size="content"
              key={candidate.relPath}
              type="button"
              onClick={() => setSelected(candidate.relPath)}
              className={`flex w-full items-center gap-2 rounded-none px-2 py-row-pad text-left font-mono text-micro transition-colors ${
                file?.relPath === candidate.relPath
                  ? "bg-accent-muted text-accent-muted-foreground"
                  : "text-muted-foreground hover:bg-interactive hover:text-foreground"
              }`}
            >
              <FileText className="size-icon-sm flex-none" aria-hidden />
              <span className="truncate" title={candidate.name}>
                {molplotDisplayName(candidate.name)}
              </span>
            </WorkbenchAction>
          ))}
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-auto p-4">
        {file && (
          <div className="mb-3 flex items-center justify-between gap-3 text-micro text-muted-foreground">
            <span className="truncate font-medium text-foreground" title={file.relPath}>
              {molplotDisplayName(file.name)}
            </span>
          </div>
        )}
        {loading && <p className="text-body text-muted-foreground">Loading plot…</p>}
        {error && (
          <EmptyState
            density="compact"
            icon={<BarChart3 className="size-icon-lg" />}
            title="Cannot render this plot"
            description="This file could not be opened as a chart."
          />
        )}
        {spec && (
          <div className="min-h-96">
            <MolplotRawChart
              spec={{ spec }}
              style={{ width: "100%", height: "var(--spacing-chart-lg)" }}
            />
          </div>
        )}
      </main>
    </div>
  );
};
