/**
 * A structure file's preview: the MolVis stage — the run view's scene (L14),
 * on the page ground, with the frame player when the file has frames.
 *
 * There is no 2D structural formula here. A formula is shown only when it is
 * asked for explicitly (one monomer, one molecule), never guessed from the
 * file; nothing asks for one yet.
 */

import { useMemo, useState } from "react";
import type { FilePreviewContentProps } from "@/plugins/types";
import { MolvisErrorBoundary } from "./MolvisErrorBoundary";
import { DEFAULT_STYLE } from "./sceneStyle";
import { type SceneSource, TrajectoryViewer } from "./TrajectoryViewer";

export const StructurePreview = ({ content, name }: FilePreviewContentProps): JSX.Element => {
  const source = useMemo<SceneSource>(() => ({ kind: "text", name, content }), [name, content]);
  const [failure, setFailure] = useState<string | null>(null);
  return (
    <div className="relative flex h-full min-h-48 flex-col bg-background">
      {failure ? (
        <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-label text-destructive">
          {failure}
        </div>
      ) : (
        <MolvisErrorBoundary key={name}>
          <TrajectoryViewer
            source={source}
            style={DEFAULT_STYLE}
            onLoaded={() => setFailure(null)}
            onFailed={setFailure}
          />
        </MolvisErrorBoundary>
      )}
    </div>
  );
};
