import type { RunTabBadgeContext } from "@/lib/contribution-types";
import { countMetricKeys } from "@/plugins/molplot/metric-cards";
import { readExecutionMetrics } from "@/plugins/molplot/read-metrics";
import { STEP_INTERVAL } from "@/plugins/molplot/resolution";

/**
 * How many keys the Metrics tab would show, of every record type — a scalar
 * series, a histogram, a text log, a JSON value or an image gallery each count.
 *
 * The count of *keys*, not of matched files: two logs of the same run share
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
    const count = countMetricKeys(read.records);
    return count > 0 ? count : null;
  } catch {
    return null;
  }
};
