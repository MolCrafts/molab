import { Profiler, type ProfilerOnRenderCallback, type ReactNode } from "react";

export interface RouteProfileSample {
  id: string;
  phase: "mount" | "update" | "nested-update";
  actualDuration: number;
  baseDuration: number;
  startTime: number;
  commitTime: number;
}

declare global {
  interface Window {
    __MOLAB_REACT_PROFILE__?: RouteProfileSample[];
    __MOLAB_ROUTE_RESOURCES__?: string[];
    __MOLAB_ROUTE_REQUESTS__?: Record<string, number>;
  }
}

const recordCommit: ProfilerOnRenderCallback = (
  id,
  phase,
  actualDuration,
  baseDuration,
  startTime,
  commitTime,
) => {
  const samples = window.__MOLAB_REACT_PROFILE__ ?? [];
  samples.push({ id, phase, actualDuration, baseDuration, startTime, commitTime });
  window.__MOLAB_REACT_PROFILE__ = samples.slice(-200);
  const requestPaths = performance
    .getEntriesByType("resource")
    .map((entry) => entry.name)
    .filter((url) => url.includes("/api/"))
    .map((url) => {
      const parsed = new URL(url);
      return `${parsed.pathname}${parsed.search}`;
    });
  const resources = Array.from(new Set(requestPaths));
  const requests = requestPaths.reduce<Record<string, number>>((counts, path) => {
    counts[path] = (counts[path] ?? 0) + 1;
    return counts;
  }, {});
  window.__MOLAB_ROUTE_RESOURCES__ = resources;
  window.__MOLAB_ROUTE_REQUESTS__ = requests;
  try {
    window.localStorage.setItem(
      "molab.react-profile",
      JSON.stringify(window.__MOLAB_REACT_PROFILE__),
    );
    window.localStorage.setItem("molab.route-resources", JSON.stringify(resources));
    window.localStorage.setItem("molab.route-requests", JSON.stringify(requests));
  } catch {
    // Private browsing / quota failures must not affect the profiled surface.
  }
};

/**
 * Opt-in React Profiler harness. Add `?profile=1` and read
 * `window.__MOLAB_REACT_PROFILE__`; normal paths add no Profiler subtree.
 */
export const RouteProfiler = ({ id, children }: { id: string; children: ReactNode }): ReactNode => {
  const enabled = new URLSearchParams(window.location.search).has("profile");
  return enabled ? (
    <Profiler id={id} onRender={recordCommit}>
      {children}
    </Profiler>
  ) : (
    children
  );
};
