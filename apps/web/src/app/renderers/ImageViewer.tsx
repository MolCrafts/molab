/**
 * An image file (Figma L07-6): centred on a checkerboard, fitted to the editor;
 * its pixel size and bytes in one muted line. Fit / 100% and Download are icons
 * in the tab row (icon OR text). No header row — the tab names the file. The
 * bytes are a TanStack query.
 */

import { useQuery } from "@tanstack/react-query";
import { Download, Maximize2 } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { workspaceApi } from "@/api";
import { EditorActions } from "@/app/shell/editorActions";
import { workspaceFileBlobQueryOptions } from "@/app/state/entityQueries";
import type { RendererProps } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
  WorkbenchToggleAction,
} from "@/components/workbench";
import { formatBytes } from "@/lib/format-bytes";
import { cn } from "@/lib/utils";

const CHECKERBOARD =
  "[background-color:var(--molab-background)] [background-image:linear-gradient(45deg,var(--molab-muted)_25%,transparent_25%),linear-gradient(-45deg,var(--molab-muted)_25%,transparent_25%),linear-gradient(45deg,transparent_75%,var(--molab-muted)_75%),linear-gradient(-45deg,transparent_75%,var(--molab-muted)_75%)] [background-size:16px_16px] [background-position:0_0,0_8px,8px_-8px,-8px_0]";

export const ImageViewer = ({ selection }: RendererProps): JSX.Element => {
  const path = selection.objectType === "workspace-file" ? selection.objectId : "";
  const query = useQuery({ ...workspaceFileBlobQueryOptions(path), enabled: Boolean(path) });
  const url = useMemo(() => (query.data ? URL.createObjectURL(query.data) : null), [query.data]);
  useEffect(() => () => (url ? URL.revokeObjectURL(url) : undefined), [url]);
  const [fit, setFit] = useState(true);
  const [pixels, setPixels] = useState<{ width: number; height: number } | null>(null);
  const name = path.split("/").pop() ?? path;

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <EditorActions>
        <div className="flex items-center gap-hairline">
          <WorkbenchToggleAction
            label={fit ? "Actual size" : "Fit"}
            pressed={fit}
            onClick={() => setFit((value) => !value)}
          >
            <Maximize2 aria-hidden className="size-icon" />
          </WorkbenchToggleAction>
          <WorkbenchIconAction label="Download" asChild>
            <a href={workspaceApi.downloadUrl(path)} download={name}>
              <Download aria-hidden />
            </a>
          </WorkbenchIconAction>
        </div>
      </EditorActions>
      <div
        className={cn(
          "flex min-h-0 flex-1 flex-col items-center justify-center overflow-auto p-4",
          CHECKERBOARD,
        )}
      >
        {query.isPending ? (
          <WorkbenchOperationState kind="loading" title="Loading image…" />
        ) : query.isError ? (
          <WorkbenchOperationState
            kind="error"
            title="Could not load image"
            detail={query.error instanceof Error ? query.error.message : path}
            action={<WorkbenchRetryAction onClick={() => void query.refetch()} />}
          />
        ) : url ? (
          <>
            <img
              src={url}
              alt={name}
              onLoad={(event) =>
                setPixels({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                })
              }
              className={cn(
                "mol-motion-enter-fade",
                fit ? "max-h-full min-h-0 max-w-full object-contain" : "max-w-none",
              )}
            />
            <p className="mt-2 flex-none text-label tabular-nums text-muted-foreground">
              {pixels ? `${pixels.width} × ${pixels.height} · ` : ""}
              {formatBytes(query.data?.size ?? null)}
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
};
