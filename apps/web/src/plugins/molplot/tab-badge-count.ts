import { workspaceApi } from "@/app/state/api";
import type { RunTabBadgeContext } from "@/lib/contribution-types";

/** Scalar-series count for the Metrics tab badge (not matched-file count). */
export const resolveMolplotMetricsTabBadgeCount = async (
  ctx: RunTabBadgeContext,
): Promise<number | null> => {
  try {
    const response = await workspaceApi.getRunMetrics(ctx.projectId, ctx.experimentId, ctx.runId);
    const keys = new Set<string>();
    for (const record of response.records) {
      if (record.t === "scalar" && typeof record.k === "string") keys.add(record.k);
    }
    return keys.size > 0 ? keys.size : response.series.length;
  } catch {
    return null;
  }
};
