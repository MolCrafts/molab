/**
 * molplot plugin tab — data-driven when MolRec / plot artifacts are present.
 *
 * Vega-Lite artifacts (``*.mlp.vl.json``) render directly through MolPlot.
 * MolRec Zarr ``observables/`` arrays are not opened in-browser yet.
 */

import type { VegaLiteSpec } from "@molcrafts/molplot";
import { useSuspenseQuery } from "@tanstack/react-query";
import { BarChart3, FileText } from "lucide-react";
import type { JSX } from "react";
import { useMemo, useState } from "react";
import { EmptyState } from "@/app/components/entity";
import { runFileTextQueryOptions } from "@/app/state/entityQueries";
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

  const run = useMemo(
    () => snapshot.runs.find((item) => item.id === selection.objectId) ?? null,
    [selection.objectId, snapshot.runs],
  );

  const file = discoveredFiles.find((f) => f.relPath === selected) ?? discoveredFiles[0];

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="flex w-56 flex-none flex-col border-r border-border bg-background">
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
        {file && run && executionId ? (
          <PlotArtifact
            projectId={run.projectId}
            experimentId={run.experimentId}
            runId={run.id}
            executionId={executionId}
            path={file.relPath}
          />
        ) : (
          <EmptyState title="Select a plot" />
        )}
      </main>
    </div>
  );
};

/** A cached artifact read suspends the tab transition until the chart data is ready. */
const PlotArtifact = ({
  projectId,
  experimentId,
  runId,
  executionId,
  path,
}: {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
  path: string;
}): JSX.Element => {
  const { data: spec } = useSuspenseQuery({
    ...runFileTextQueryOptions(projectId, experimentId, runId, executionId, path),
    select: (content): VegaLiteSpec => {
      const parsed: unknown = JSON.parse(content);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("The plot artifact is not a Vega-Lite object.");
      return parsed as VegaLiteSpec;
    },
  });
  return (
    <div className="min-h-96">
      <MolplotRawChart
        spec={{ spec }}
        style={{ width: "100%", height: "var(--spacing-chart-lg)" }}
      />
    </div>
  );
};
