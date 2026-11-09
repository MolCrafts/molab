/**
 * The MolVis scene of a run view: one structure or trajectory of the attempt,
 * drawn by molvis-stage on the page ground with none of the stage's own chrome,
 * and the frame player under it when there is more than one frame.
 */

import type { Molvis } from "@molcrafts/molvis-stage";
import { useEffect, useRef, useState } from "react";
import { FramePlayer } from "./FramePlayer";
import { collectZarrStore, scopedZarrSource, workspaceZarrSource } from "./host-zarr";
import { loadMolvisCore, type MolvisCore } from "./loadMolvisCore";
import {
  applyAxes,
  applyGround,
  applyPipelineStyle,
  applyProjection,
  atomColumns,
  SCENE_CONFIG,
} from "./sceneControls";
import { useSceneGround } from "./sceneGround";
import type { MolvisStyle } from "./sceneStyle";

/** What the scene draws: a file's text, or a `*.mrec` store under the attempt. */
export type SceneSource =
  | { kind: "text"; name: string; content: string }
  | { kind: "mrec"; name: string; storeRoot: string; attemptDir: string };

/** What the loaded scene can be styled with. */
export interface SceneInfo {
  representations: readonly { id: string; name: string }[];
  columns: readonly string[];
}

interface TrajectoryViewerProps {
  source: SceneSource;
  style: MolvisStyle;
  onLoaded: (info: SceneInfo) => void;
  onFailed: (message: string) => void;
}

interface Stage {
  app: Molvis;
  core: MolvisCore;
}

const message = (reason: unknown): string =>
  reason instanceof Error ? reason.message : String(reason);

const loadSource = async (core: MolvisCore, app: Molvis, source: SceneSource): Promise<void> => {
  const target = app as unknown as Parameters<MolvisCore["loadFileContent"]>[0];
  if (source.kind === "text") {
    await core.loadFileContent(target, source.content, source.name);
    return;
  }
  const store = scopedZarrSource(workspaceZarrSource(source.attemptDir), source.storeRoot);
  if (core.loadDirectory) {
    await core.loadDirectory(target, store, source.name);
    return;
  }
  await core.loadFileContent(target, await collectZarrStore(store), source.name);
};

export const TrajectoryViewer = ({
  source,
  style,
  onLoaded,
  onFailed,
}: TrajectoryViewerProps): JSX.Element => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [stage, setStage] = useState<Stage | null>(null);
  const ground = useSceneGround();
  const groundRef = useRef(ground);
  groundRef.current = ground;
  const callbacks = useRef({ onLoaded, onFailed });
  callbacks.current = { onLoaded, onFailed };

  const sourceKey =
    source.kind === "text"
      ? `text:${source.name}:${source.content}`
      : `mrec:${source.attemptDir}:${source.storeRoot}`;

  // biome-ignore lint/correctness/useExhaustiveDependencies: `sourceKey` is the source's identity
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let mounted: Molvis | null = null;
    const lost = (): void => callbacks.current.onFailed("The 3D view lost its graphics context.");
    setStage(null);
    const run = async (): Promise<void> => {
      try {
        const core = await loadMolvisCore();
        if (cancelled) return;
        const app = core.mountMolvis(container, SCENE_CONFIG);
        mounted = app;
        app.canvas.addEventListener("webglcontextlost", lost);
        applyGround(app, groundRef.current);
        app.enableFitContainer(true);
        await app.start();
        if (cancelled) return;
        await loadSource(core, app, source);
        if (cancelled) return;
        setStage({ app, core });
        callbacks.current.onLoaded({
          representations: core.representations.map(({ id, name }) => ({ id, name })),
          columns: atomColumns(app),
        });
      } catch (reason) {
        if (!cancelled) callbacks.current.onFailed(message(reason));
      }
    };
    void run();
    return () => {
      cancelled = true;
      if (!mounted) return;
      mounted.canvas.removeEventListener("webglcontextlost", lost);
      try {
        applyAxes(mounted, true);
        mounted.destroy();
      } catch {
        // The canvas goes away with the view.
      }
    };
  }, [sourceKey]);

  useEffect(() => {
    if (stage) applyGround(stage.app, ground);
  }, [stage, ground]);

  const { model, bonds, cell, colourBy, projection, axes } = style;
  useEffect(() => {
    if (!stage) return;
    applyPipelineStyle(stage.app, stage.core, { model, bonds, cell, colourBy }).catch((reason) =>
      callbacks.current.onFailed(message(reason)),
    );
  }, [stage, model, bonds, cell, colourBy]);

  useEffect(() => {
    if (stage) applyProjection(stage.app, projection);
  }, [stage, projection]);

  useEffect(() => {
    if (stage) applyAxes(stage.app, axes);
  }, [stage, axes]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* `isolate` keeps the stage's own layers (its context menu) under the molab chrome. */}
      <div className="relative isolate min-h-0 flex-1 overflow-hidden bg-background">
        <div ref={containerRef} className="absolute inset-0" />
        {stage ? null : (
          <div
            role="status"
            className="absolute inset-0 flex items-center justify-center text-label text-muted-foreground"
          >
            Loading {source.name}…
          </div>
        )}
      </div>
      {stage ? <FramePlayer app={stage.app} speed={style.speed} /> : null}
    </div>
  );
};
