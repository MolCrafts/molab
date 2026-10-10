/**
 * Which files molplot will draw — answered by the reader registry.
 *
 * molplot owns no format and parses nothing. A package that can read one
 * contributes a reader (molrs reads solver logs in WASM, in the browser), and
 * this module only asks the registry whether anything claims a file.
 *
 * The patterns a reader declares are a *hint*, used to decide whether to
 * offer the tab without fetching anything. The reader's own content check has
 * the final say once the bytes are in hand, so a hint that is slightly too
 * narrow costs a tab the user can still reach, while one that is too broad
 * would offer an empty chart.
 */

import {
  listMetricReaderContributions,
  resolveMetricReaderForPath,
} from "@/lib/contribution-runtime";

/** True when some contributed reader claims this file by name. */
export const isMetricSurface = (file: { name: string; relPath: string }): boolean =>
  resolveMetricReaderForPath(file.relPath) !== undefined ||
  resolveMetricReaderForPath(file.name) !== undefined;

/** Every format currently contributed, for the format picker. */
export const knownMetricFormats = (): { format: string; label: string }[] =>
  listMetricReaderContributions().map(({ format, label }) => ({ format, label }));
