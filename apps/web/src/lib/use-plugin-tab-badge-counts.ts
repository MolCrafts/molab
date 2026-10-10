import { useEffect, useState } from "react";
import type { RunTabBadgeContext } from "@/lib/contribution-types";
import type { DiscoveredPlugin } from "@/lib/file-type-discovery";

/**
 * Catalog badge counts keyed by file-type contribution ``value``.
 * Only contributions with ``resolveTabBadgeCount`` are fetched.
 */
export const usePluginTabBadgeCounts = (
  discovered: DiscoveredPlugin[],
  coords: RunTabBadgeContext | null,
): Readonly<Record<string, number | null>> => {
  const [counts, setCounts] = useState<Record<string, number | null>>({});
  const projectId = coords?.projectId ?? null;
  const experimentId = coords?.experimentId ?? null;
  const runId = coords?.runId ?? null;
  const executionId = coords?.executionId ?? null;

  useEffect(() => {
    if (!projectId || !experimentId || !runId || !executionId) {
      setCounts({});
      return;
    }
    const context: RunTabBadgeContext = { projectId, experimentId, runId, executionId };

    const withResolver = discovered.filter(({ contribution }) => contribution.resolveTabBadgeCount);
    if (withResolver.length === 0) {
      setCounts({});
      return;
    }

    let cancelled = false;
    void (async () => {
      const next: Record<string, number | null> = {};
      await Promise.all(
        withResolver.map(async ({ contribution }) => {
          const resolver = contribution.resolveTabBadgeCount;
          if (!resolver) return;
          next[contribution.value] = await resolver(context);
        }),
      );
      if (!cancelled) setCounts(next);
    })();

    return () => {
      cancelled = true;
    };
  }, [discovered, executionId, experimentId, projectId, runId]);

  return counts;
};
