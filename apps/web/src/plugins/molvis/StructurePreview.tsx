import { useEffect, useMemo, useRef, useState } from "react";
import type { FilePreviewContentProps } from "@/plugins/types";
import { loadMolvisCore } from "./loadMolvisCore";
import { MolvisErrorBoundary } from "./MolvisErrorBoundary";
import { parseStructure } from "./structureGraph";
import { structureSvg } from "./structureSvg";

interface MolvisHandle {
  destroy?: () => void;
  enableFitContainer?: (enabled: boolean) => void;
  start?: () => Promise<void> | void;
}

type StageState = { kind: "loading" } | { kind: "ready" } | { kind: "error"; message: string };

const SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉";

const Formula = ({ value }: { value: string }): JSX.Element => (
  <p className="shrink-0 px-3 pt-3 font-mono text-body-lg text-foreground">
    {value.replace(/\d/g, (digit) => SUBSCRIPTS[Number(digit)] ?? digit)}
  </p>
);

const Stage = ({ name, content }: { name: string; content: string }): JSX.Element => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const appRef = useRef<MolvisHandle | null>(null);
  const [state, setState] = useState<StageState>({ kind: "loading" });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    setState({ kind: "loading" });
    const run = async (): Promise<void> => {
      try {
        const { mountMolvis, loadFileContent } = await loadMolvisCore();
        if (cancelled) return;
        const app = mountMolvis(container) as unknown as MolvisHandle;
        appRef.current = app;
        app.enableFitContainer?.(true);
        await app.start?.();
        if (cancelled) return;
        await loadFileContent(app as never, content, name);
        if (!cancelled) setState({ kind: "ready" });
      } catch (reason) {
        if (!cancelled) {
          setState({
            kind: "error",
            message: reason instanceof Error ? reason.message : String(reason),
          });
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
      const app = appRef.current;
      appRef.current = null;
      try {
        app?.destroy?.();
      } catch {
        // The canvas is going away with the preview.
      }
    };
  }, [name, content]);

  return (
    <div className="relative min-h-48 flex-1 bg-canvas">
      <div ref={containerRef} className="absolute inset-0" />
      {state.kind === "loading" ? (
        <div className="absolute inset-0 flex items-center justify-center text-label text-muted-foreground">
          Loading 3D…
        </div>
      ) : null}
      {state.kind === "error" ? (
        <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-label text-destructive">
          {state.message}
        </div>
      ) : null}
    </div>
  );
};

/** 2D structural formula beside the 3D model for one structure file. */
export const StructurePreview = ({ content, name }: FilePreviewContentProps): JSX.Element => {
  const graph = useMemo(() => parseStructure(name, content), [name, content]);
  const diagram = useMemo(() => {
    if (!graph || graph.atoms.length === 0) return null;
    try {
      return structureSvg(graph);
    } catch (reason) {
      return reason instanceof Error ? reason.message : "Could not draw the formula";
    }
  }, [graph]);
  const svg = diagram?.startsWith("<svg") ? diagram : null;
  const [svgUrl, setSvgUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!svg) {
      setSvgUrl(null);
      return;
    }
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    setSvgUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [svg]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {graph?.formula ? <Formula value={graph.formula} /> : null}
      <div className="grid min-h-0 flex-1 grid-rows-[minmax(9rem,0.8fr)_minmax(12rem,1.2fr)]">
        <div className="flex min-h-0 items-center justify-center overflow-auto border-b border-border bg-background px-3 py-2">
          {svgUrl ? (
            <img
              src={svgUrl}
              alt={graph?.formula ? `Structural formula ${graph.formula}` : "Structural formula"}
              className="max-h-full max-w-full object-contain"
            />
          ) : (
            <p className="text-label text-muted-foreground">
              {svg ? "Drawing formula…" : (diagram ?? "No bond table for a 2D formula.")}
            </p>
          )}
        </div>
        <MolvisErrorBoundary key={name}>
          <Stage name={name} content={content} />
        </MolvisErrorBoundary>
      </div>
    </div>
  );
};
