/**
 * Which of an attempt's files MolPlot reads, and its view's count badge.
 *
 * molplot owns no format: a file is a metric source when some contributed
 * reader claims it (`isMetricSurface`), and a figure when it is a run's own
 * Vega-Lite plot (`*.mlp.vl.json`, molplot's artifact, so a literal pattern).
 */

import type { AttemptFile, FileTypeMatcher, RunAttempt } from "@molcrafts/molab-plugin";
import { isMetricSurface } from "./metric-formats";
import { readExecutionMetrics } from "./read-metrics";
import { STEP_INTERVAL } from "./resolution";
import { buildScalarSeries } from "./scalar-series";

const FIGURE_SUFFIX = ".mlp.vl.json";

/** A run's own Vega-Lite figure. */
export const isFigureFile = (file: { name: string; relPath: string }): boolean =>
  file.name.toLowerCase().endsWith(FIGURE_SUFFIX) ||
  file.relPath.toLowerCase().replace(/\\/g, "/").endsWith(FIGURE_SUFFIX);

export const MOLPLOT_FILES: FileTypeMatcher = {
  patterns: ["**/*.mlp.vl.json", "*.mlp.vl.json"],
  matches: (file) => isMetricSurface(file) || isFigureFile(file),
};

/**
 * The badge: how many panels the default figure draws — one per distinct
 * series key across the attempt's sources, plus one per figure file.
 *
 * Read at the view's own step resolution, so the badge cannot promise a
 * series the figure then thins away; the readers cache by `path@revision`,
 * so opening the view afterwards re-slices rather than re-parses.
 */
export const countPanels = async (
  attempt: RunAttempt,
  files: readonly AttemptFile[],
): Promise<number | null> => {
  const figures = files.filter(isFigureFile).length;
  try {
    const read = await readExecutionMetrics(attempt, { stepInterval: STEP_INTERVAL });
    const keys = new Set(buildScalarSeries(read.records).map((series) => series.key));
    const count = keys.size + figures;
    return count > 0 ? count : null;
  } catch {
    return figures > 0 ? figures : null;
  }
};
