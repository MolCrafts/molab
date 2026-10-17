const SECTION_LABELS = new Set(["TEXMFLOG:", "MISSFONTLOG:", "LOG:", "STDOUT:", "STDERR:"]);

/** One line of an engine log, short enough for the error banner. */
export const logSummary = (log: string): string => {
  const lines = log
    .split("\n")
    .map((item) => item.trim())
    .filter((item) => item.length > 0 && !/^=+$/.test(item) && !SECTION_LABELS.has(item));
  const error = [...lines].reverse().find((item) => item.startsWith("!"));
  const line =
    error ??
    [...lines].reverse().find((item) => !item.startsWith("EXITCODE:") && !item.startsWith("$ ")) ??
    "";
  if (line.length === 0) return "The engine returned no PDF.";
  return line.length > 240 ? `${line.slice(0, 240)}…` : line;
};
