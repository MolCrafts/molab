/**
 * Pure helpers behind `<molab-log>`: which stream a file is, the `lines`
 * range, and the numbered excerpt with its error lines marked.
 */

import type { LogStream } from "@/app/state/executionLog";

export interface LineRange {
  /** 1-based, inclusive. */
  from: number;
  to: number;
}

export interface ExcerptLine {
  number: number;
  text: string;
  error: boolean;
}

/** Lines shown when no `lines` range is written: the end of the log. */
export const DEFAULT_TAIL = 12;

const ERROR_LINE = /error|traceback|exception/i;

export const isErrorLine = (text: string): boolean => ERROR_LINE.test(text);

/** `1182-1185` (also `1182–1185`, `1182:1185`) or `1184` → a range; anything else null. */
export const parseLineRange = (text: string | undefined): LineRange | null => {
  const match = /^\s*(\d+)\s*(?:[-–:]\s*(\d+))?\s*$/.exec(text ?? "");
  if (!match) return null;
  const from = Number(match[1]);
  const to = match[2] === undefined ? from : Number(match[2]);
  if (from < 1 || to < from) return null;
  return { from, to };
};

/** `run.log` / `stdout.log` / `stderr.log` → the stream the log API reads; else null. */
export const streamOfFile = (file: string): LogStream | null => {
  if (file === "run.log") return "run";
  if (file === "stdout.log") return "stdout";
  if (file === "stderr.log") return "stderr";
  return null;
};

const splitLines = (text: string): string[] => {
  const lines = text.split(/\r?\n/);
  return lines.length > 0 && lines[lines.length - 1] === "" ? lines.slice(0, -1) : lines;
};

/** The numbered lines of *range*, or the last `DEFAULT_TAIL` lines when there is none. */
export const excerptLines = (text: string, range: LineRange | null): ExcerptLine[] => {
  const lines = splitLines(text);
  const from = range ? range.from : Math.max(1, lines.length - DEFAULT_TAIL + 1);
  const to = range ? Math.min(range.to, lines.length) : lines.length;
  return lines
    .slice(from - 1, to)
    .map((line, index) => ({ number: from + index, text: line, error: isErrorLine(line) }));
};
