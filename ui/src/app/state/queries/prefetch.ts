/**
 * Hover/focus-intent prefetching for navigator rows and list rows.
 *
 * Returns handlers to spread onto a row. The prefetch fires after `delayMs`
 * of sustained hover/focus and is cancelled on leave/blur, so a mouse sweeping
 * down a list issues nothing. Repeated hovers are cheap: `prefetchQuery`
 * honours `staleTime`, so a warm key is a no-op.
 */

import { useCallback, useEffect, useRef } from "react";

export interface PrefetchIntentHandlers {
  onMouseEnter: () => void;
  onFocus: () => void;
  onMouseLeave: () => void;
  onBlur: () => void;
}

export function usePrefetchOnIntent(
  prefetch: () => unknown,
  { delayMs = 120 }: { delayMs?: number } = {},
): PrefetchIntentHandlers {
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef(prefetch);
  latest.current = prefetch;

  const disarm = useCallback((): void => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const arm = useCallback((): void => {
    if (timer.current !== null) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      void Promise.resolve(latest.current()).catch(() => {
        // Prefetch failures are silent by design — the real query reports.
      });
    }, delayMs);
  }, [delayMs]);

  useEffect(() => disarm, [disarm]);

  return { onMouseEnter: arm, onFocus: arm, onMouseLeave: disarm, onBlur: disarm };
}
