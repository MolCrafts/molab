import { type JSX, useState } from "react";
import type { RendererProps } from "@/app/types";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";

/** The streaming blob endpoint — the browser fetches and caches this itself. */
const blobUrl = (path: string, attempt: number): string => {
  const base = `/api/workspace/file/blob?path=${encodeURIComponent(path)}`;
  // Retry busts the HTTP cache; the first load must stay cacheable.
  return attempt === 0 ? base : `${base}&retry=${attempt}`;
};

/**
 * Preview a workspace image.
 *
 * The element points straight at the blob endpoint rather than fetching a Blob
 * and wrapping it in an object URL: the browser then streams it, caches it
 * across revisits, and decodes it off the main thread. The previous version
 * pulled the whole image into JS memory on every mount and threw the cache
 * away with the object URL.
 */
export const ImageViewer = ({ selection }: RendererProps): JSX.Element => {
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  if (selection.objectType !== "workspace-file") {
    return (
      <div className="flex h-full items-center justify-center p-3">
        <WorkbenchOperationState kind="empty" title="No image selected" />
      </div>
    );
  }

  const src = blobUrl(selection.objectId, attempt);

  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <header className="flex h-10 flex-none items-center border-b border-border px-3">
        <p className="min-w-0 truncate font-mono text-label text-muted-foreground tabular-nums">
          {selection.objectId}
        </p>
      </header>
      <div className="flex min-h-0 flex-1 items-center justify-center p-3">
        {failed ? (
          <WorkbenchOperationState
            kind="error"
            title="Could not load image"
            detail={selection.objectId}
            action={
              <WorkbenchRetryAction
                onClick={() => {
                  setFailed(false);
                  setLoaded(false);
                  setAttempt((value) => value + 1);
                }}
              />
            }
          />
        ) : (
          <>
            {!loaded && <WorkbenchOperationState kind="loading" title="Loading image…" />}
            <img
              // Keyed by src so a retry remounts rather than reusing the
              // element's failed state.
              key={src}
              src={src}
              alt={selection.objectId}
              loading="lazy"
              decoding="async"
              onLoad={() => setLoaded(true)}
              onError={() => setFailed(true)}
              className={`mol-motion-enter-fade max-h-full max-w-full object-contain ${
                loaded ? "" : "hidden"
              }`}
            />
          </>
        )}
      </div>
    </div>
  );
};
