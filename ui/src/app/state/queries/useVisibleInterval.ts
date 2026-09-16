/**
 * `setInterval` that pauses while the document is hidden.
 *
 * For clock ticks and other render-only timers. Data refreshes belong to a
 * query's `refetchInterval`, which the client already pauses in the background.
 */

import { useEffect, useRef } from "react";

export function useVisibleInterval(callback: () => void, delayMs: number | null): void {
  const latest = useRef(callback);
  latest.current = callback;

  useEffect(() => {
    if (delayMs === null) return;

    let timer: ReturnType<typeof setInterval> | null = null;

    const stop = (): void => {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    };
    const start = (): void => {
      if (timer === null) timer = setInterval(() => latest.current(), delayMs);
    };
    const sync = (): void => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") stop();
      else start();
    };

    sync();
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", sync);
    }
    return () => {
      stop();
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", sync);
      }
    };
  }, [delayMs]);
}
