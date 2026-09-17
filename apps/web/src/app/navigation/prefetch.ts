import type { LeftPanelView } from "@/app/types";
import { prefetchLazy, prefetchOnIdle } from "@/lib/lazy-with-prefetch";
import { getNavigationContribution, listNavigationContributions } from "./sections";

/** Start loading a rail section's explorer and landing chunks before click. */
export const prefetchNavigationView = (id: LeftPanelView): void => {
  const contribution = getNavigationContribution(id);
  prefetchLazy(contribution.explorer);
  prefetchLazy(contribution.landing);
};

/** After first paint, warm the primary rail so switching sections is a cache hit. */
export const prefetchPrimaryNavigationOnIdle = (): void => {
  prefetchOnIdle(() => {
    for (const contribution of listNavigationContributions()) {
      if (contribution.placement !== "primary") continue;
      prefetchLazy(contribution.explorer);
      prefetchLazy(contribution.landing);
    }
  });
};
