import { type ComponentType, type LazyExoticComponent, lazy } from "react";

/**
 * `React.lazy` that shares one module promise between first render and
 * intent prefetch (hover / focus / idle). Calling `prefetch()` starts the
 * dynamic import so a later click does not wait on the network.
 */
// Host slots pass concrete props; `any` matches `React.lazy` / PluginComponent.
// biome-ignore lint/suspicious/noExplicitAny: same variance as React.lazy
export type PrefetchableComponent<T extends ComponentType<any> = ComponentType<any>> =
  LazyExoticComponent<T> & { prefetch: () => Promise<{ default: T }> };

// biome-ignore lint/suspicious/noExplicitAny: same variance as React.lazy
export const lazyWithPrefetch = <T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
): PrefetchableComponent<T> => {
  let pending: Promise<{ default: T }> | undefined;
  const load = (): Promise<{ default: T }> => {
    pending ??= factory();
    return pending;
  };
  const Component = lazy(load) as PrefetchableComponent<T>;
  Component.prefetch = load;
  return Component;
};

export const prefetchLazy = (component: unknown): void => {
  if (
    component !== null &&
    typeof component === "object" &&
    "prefetch" in component &&
    typeof (component as { prefetch: unknown }).prefetch === "function"
  ) {
    void (component as { prefetch: () => unknown }).prefetch();
  }
};

export const prefetchOnIdle = (run: () => void): void => {
  if (typeof window === "undefined") return;
  const idle = window.requestIdleCallback;
  if (typeof idle === "function") {
    idle(() => run(), { timeout: 2500 });
    return;
  }
  window.setTimeout(run, 1);
};
