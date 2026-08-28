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

  useEffect(() => {
    if (!coords) {
      setCounts({});
      return;
    }

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
          next[contribution.value] = await resolver(coords);
        }),
      );
      if (!cancelled) setCounts(next);
    })();

    return () => {
      cancelled = true;
    };
  }, [discovered, coords?.projectId, coords?.experimentId, coords?.runId]);

  return counts;
};
