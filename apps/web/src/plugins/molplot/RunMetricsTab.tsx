import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@molcrafts/ui";
import { AlertTriangle } from "lucide-react";
import { type JSX, useState } from "react";
import { EmptyState } from "@/app/components/entity";
import { ImageViewer } from "@/app/renderers/ImageViewer";
import type { RendererProps, WorkspaceFileSelection } from "@/app/types";
import { RunMetricsView } from "@/plugins/molplot/RunMetricsView";
import type { DiscoveredFile } from "@/plugins/types";

type RunMetricsTabProps = RendererProps & { discoveredFiles?: DiscoveredFile[] };

/**
 * Workspace-explorer metrics tab: a thin wrapper that resolves the run from
 * the workspace `snapshot` and delegates rendering to the coord-driven
 * {@link RunMetricsView}. The metrics rendering core lives in RunMetricsView
 * so the runs-dashboard `RunInspector` can reuse it without `snapshot.runs`.
 *
 * An image card opens the image in the existing `ImageViewer`, addressed by
 * the attempt directory the server reported (`executionDir`) plus the
 * record's attempt-relative path.
 */
export const RunMetricsTab = (props: RunMetricsTabProps): JSX.Element => {
  const { selection, snapshot, executionId, executionDir } = props;
  const [openImage, setOpenImage] = useState<string | null>(null);
  const run = snapshot.runs.find((item) => item.id === selection.objectId) ?? null;

  if (!run || !executionId) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<AlertTriangle className="h-6 w-6" />}
          title={run ? "Select an execution" : "Run not found"}
          description={
            run
              ? "MolPlot data belongs to one physical execution."
              : "It may have been deleted or not yet synced."
          }
        />
      </div>
    );
  }

  const imageSelection: WorkspaceFileSelection | null =
    openImage && executionDir
      ? {
          objectType: "workspace-file",
          objectId: `${executionDir.replace(/\/+$/, "")}/${openImage}`,
          filePath: `${executionDir.replace(/\/+$/, "")}/${openImage}`,
          fileKind: "image",
        }
      : null;

  return (
    <>
      <RunMetricsView
        key={run.id}
        projectId={run.projectId}
        experimentId={run.experimentId}
        runId={run.id}
        executionId={executionId}
        status={run.executionHistory.find((e) => e.executionId === executionId)?.status}
        onOpenImage={executionDir ? setOpenImage : undefined}
      />
      <Dialog open={imageSelection !== null} onOpenChange={(open) => !open && setOpenImage(null)}>
        <DialogContent className="flex h-[min(80vh,48rem)] w-[min(90vw,64rem)] max-w-none flex-col overflow-hidden p-0 sm:max-w-none">
          <DialogHeader className="sr-only">
            <DialogTitle>{openImage}</DialogTitle>
          </DialogHeader>
          {imageSelection ? <ImageViewer {...props} selection={imageSelection} /> : null}
        </DialogContent>
      </Dialog>
    </>
  );
};
