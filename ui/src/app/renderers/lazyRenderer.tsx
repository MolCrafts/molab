/**
 * Code-split a centre renderer behind its own chunk.
 *
 * The renderer registry wants a plain `ComponentType<RendererProps>`, but the
 * heavy viewers (the agent stack, the flowgram canvas, Monaco) should not be in
 * the entry bundle — most sessions never open them. This wraps `React.lazy` so
 * a registration keeps its eager-looking shape while the module is fetched on
 * first render, with the workbench's standard loading surface in between.
 */

import { type ComponentType, type JSX, lazy, Suspense } from "react";
import type { RendererProps } from "@/app/types";
import { WorkbenchOperationState } from "@/components/workbench";

/**
 * Wrap a dynamic import as a registry-ready renderer.
 *
 * @param load Resolves the renderer component (a named export, not a default).
 * @param title Optional label for the loading state while the chunk arrives.
 * @returns A component that suspends on first render, then renders the module.
 */
export const lazyRenderer = (
  load: () => Promise<ComponentType<RendererProps>>,
  title = "Loading…",
): ComponentType<RendererProps> => {
  const Lazy = lazy(async () => ({ default: await load() }));

  const LazyRenderer = (props: RendererProps): JSX.Element => (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center p-6">
          <WorkbenchOperationState kind="loading" title={title} />
        </div>
      }
    >
      <Lazy {...props} />
    </Suspense>
  );
  LazyRenderer.displayName = "LazyRenderer";
  return LazyRenderer;
};
