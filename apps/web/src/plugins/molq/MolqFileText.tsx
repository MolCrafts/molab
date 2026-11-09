/**
 * A scheduler file (submit script, stdout, stderr) as the Logs view draws a
 * log: mono, numbered lines, error and warning lines in their colour. A long
 * file shows its tail — where a job's outcome is — and the editor has the rest.
 */

import { type JSX, useMemo } from "react";
import { classifyLines, type LineKind } from "@/app/renderers/logLines";
import { cn } from "@/lib/utils";

/** The most lines drawn at once; a scheduler file's end is what matters. */
export const MAX_LINES = 5_000;

const KIND_CLASS: Record<Exclude<LineKind, null>, string> = {
  error: "text-status-failed-foreground",
  warning: "text-status-warning-foreground",
};

/** The file's lines, without the empty one after a final newline. */
export const textLines = (text: string): string[] => {
  const lines = text.split(/\r?\n/);
  return lines.at(-1) === "" ? lines.slice(0, -1) : lines;
};

export const MolqFileText = ({ text }: { text: string }): JSX.Element => {
  const { lines, kinds, offset } = useMemo(() => {
    const all = textLines(text);
    const allKinds = classifyLines(all);
    const from = Math.max(0, all.length - MAX_LINES);
    return { lines: all.slice(from), kinds: allKinds.slice(from), offset: from };
  }, [text]);
  const gutter = `calc(${String(offset + lines.length).length + 1}ch + 2rem)`;
  return (
    <div className="overflow-auto rounded-control border border-border py-2 font-mono text-label">
      {offset > 0 ? (
        <div className="px-4 pb-1 text-muted-foreground">
          Lines 1–{offset} are not shown; open the file to read them.
        </div>
      ) : null}
      <ol className="min-w-max">
        {lines.map((line, index) => {
          const number = offset + index + 1;
          const kind = kinds[index] ?? null;
          return (
            <li key={number} data-line={number} className="flex h-5 items-center whitespace-pre">
              <span
                aria-hidden
                className="shrink-0 select-none px-4 text-right text-muted-foreground"
                style={{ width: gutter }}
              >
                {number}
              </span>
              <span className={cn("pr-4", kind ? KIND_CLASS[kind] : "text-foreground")}>
                {line || " "}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
};
