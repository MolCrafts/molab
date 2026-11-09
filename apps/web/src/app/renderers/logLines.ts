// ─────────────────────────────────────────────────────────────────────────────
// A log, read as lines (L04 Logs view): which lines are errors or warnings —
// the stops ↑↓ walk between — and which lines a find matches. Pure, so the
// view only scrolls and paints.
// ─────────────────────────────────────────────────────────────────────────────

export type LineKind = "error" | "warning" | null;

const ERROR = /\b(?:error|exception|fatal|critical|traceback)\b|^\S+(?:Error|Exception):/i;
const WARNING = /\bwarn(?:ing)?\b/i;

/**
 * Each line's kind. A Python traceback is one error block: its header, the
 * indented frames under it, and the exception line that closes it.
 */
export const classifyLines = (lines: readonly string[]): LineKind[] => {
  const kinds: LineKind[] = [];
  let inTraceback = false;
  for (const line of lines) {
    if (line.startsWith("Traceback")) {
      inTraceback = true;
      kinds.push("error");
      continue;
    }
    if (inTraceback) {
      kinds.push("error");
      // The first unindented line after the frames is the exception; the block ends there.
      if (line.length > 0 && !/^\s/.test(line)) inTraceback = false;
      continue;
    }
    kinds.push(ERROR.test(line) ? "error" : WARNING.test(line) ? "warning" : null);
  }
  return kinds;
};

/**
 * Where ↑↓ stop: the first line of each run of error or warning lines (a
 * traceback is one stop, not twenty), as 0-based indexes.
 */
export const lineStops = (
  kinds: readonly LineKind[],
): { errors: number; warnings: number; stops: number[] } => {
  const stops: number[] = [];
  let errors = 0;
  let warnings = 0;
  kinds.forEach((kind, index) => {
    if (!kind || kinds[index - 1] === kind) return;
    stops.push(index);
    if (kind === "error") errors += 1;
    else warnings += 1;
  });
  return { errors, warnings, stops };
};

/** 0-based indexes of the lines that contain `query`, case-insensitively. */
export const findLines = (lines: readonly string[], query: string): number[] => {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  return lines.flatMap((line, index) => (line.toLowerCase().includes(needle) ? [index] : []));
};

/** The next index in `targets` after (or before) `from`, wrapping around; null when empty. */
export const stepTo = (
  targets: readonly number[],
  from: number | null,
  direction: 1 | -1,
): number | null => {
  if (targets.length === 0) return null;
  if (from === null) return direction === 1 ? (targets[0] ?? null) : (targets.at(-1) ?? null);
  if (direction === 1) return targets.find((target) => target > from) ?? targets[0] ?? null;
  return [...targets].reverse().find((target) => target < from) ?? targets.at(-1) ?? null;
};
