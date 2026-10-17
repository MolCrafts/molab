import type { RunTabBadgeContext } from "@/lib/contribution-types";
import { readExecutionMetrics } from "@/plugins/molplot/read-metrics";
import { STEP_INTERVAL } from "@/plugins/molplot/resolution";

/**
 * How many scalar series the Metrics tab would show.
 *
 * The count of *series*, not of matched files: two logs of the same run share
 * their curves, and a file count would claim more than the tab displays.
 *
 * Read at the same step resolution the tab itself uses, so the badge cannot
 * promise a series the chart then thins away — and because the readers cache
 * by `path@revision`, opening the tab afterwards re-slices rather than
 * re-parsing.
 */
export const resolveMolplotMetricsTabBadgeCount = async (
  ctx: RunTabBadgeContext,
): Promise<number | null> => {
  try {
    const read = await readExecutionMetrics(
      {
        projectId: ctx.projectId,
        experimentId: ctx.experimentId,
        runId: ctx.runId,
        executionId: ctx.executionId,
      },
      { stepInterval: STEP_INTERVAL },
    );
    const keys = new Set<string>();
    for (const record of read.records) {
      if (record.t === "scalar" && typeof record.k === "string") {
        keys.add(record.k);
      }
    }
    return keys.size > 0 ? keys.size : null;
  } catch {
    return null;
  }
};
