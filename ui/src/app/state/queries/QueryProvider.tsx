/**
 * Provider for the app-wide query client.
 *
 * The React Query devtools are mounted only under `__DEV__` (a build-time
 * define in `rsbuild.config.ts`); the dynamic import is dead-code-eliminated
 * from production bundles. Its floating trigger is the one exception to the
 * "status lives only in the bottom status bar" rule in
 * `.claude/notes/ui-guidelines.md` — it is developer tooling that never ships.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, type ReactNode, Suspense } from "react";
import { queryClient } from "./queryClient";

const isDev = typeof __DEV__ !== "undefined" && __DEV__;

const Devtools = isDev
  ? lazy(() =>
      import("@tanstack/react-query-devtools").then((module) => ({
        default: module.ReactQueryDevtools,
      })),
    )
  : null;

export function QueryProvider({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {Devtools ? (
        <Suspense fallback={null}>
          <Devtools initialIsOpen={false} buttonPosition="bottom-left" />
        </Suspense>
      ) : null}
    </QueryClientProvider>
  );
}
