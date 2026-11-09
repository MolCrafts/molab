/**
 * The run's attempt (L14): a chip at the right end of the run's views —
 * status glyph · eNN · latest / run result — whose menu (one line per
 * attempt) switches every view, core and plugin. The URL keeps it
 * (`?attempt=eNN`; the latest when absent).
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { Check, ChevronDown } from "lucide-react";
import type { JSX } from "react";
import { StatusIcon } from "@/app/components/entity";
import type { ExecutionRecordSummary } from "@/app/types";
import { parseInstant } from "@/lib/format-time";
import { MODE_WORD, runResultExecution } from "./runStory";

const clock = (iso: string | null): string => {
  const ms = parseInstant(iso);
  if (ms === null) return "";
  const date = new Date(ms);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
};

/** “latest”, “run result”, both, or nothing. */
export const attemptWord = (
  history: readonly ExecutionRecordSummary[],
  executionId: string,
): string => {
  const latest = history.at(-1)?.executionId === executionId;
  const result = runResultExecution(history)?.execution.executionId === executionId;
  return [latest ? "latest" : "", result ? "run result" : ""].filter(Boolean).join(" · ");
};

export const RunAttemptChip = ({
  history,
  selected,
  onSelect,
}: {
  history: readonly ExecutionRecordSummary[];
  selected: string | null;
  onSelect: (executionId: string) => void;
}): JSX.Element | null => {
  const current = history.find((item) => item.executionId === selected) ?? history.at(-1);
  if (!current) return null;
  const word = attemptWord(history, current.executionId);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`Attempt ${current.executionId}${word ? `, ${word}` : ""}. Switch attempt`}
          className="flex h-6 min-w-0 flex-none items-center gap-1 self-center rounded-control border border-border bg-surface pr-1 pl-1 text-label hover:border-input"
        >
          <StatusIcon status={current.status} />
          <span className="truncate font-mono max-sm:max-w-20">{current.executionId}</span>
          {word ? <span className="text-muted-foreground max-sm:hidden">{word}</span> : null}
          <ChevronDown aria-hidden className="size-3 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        {[...history].reverse().map((attempt) => {
          const tag = attemptWord(history, attempt.executionId);
          const on = attempt.executionId === current.executionId;
          return (
            <DropdownMenuItem
              key={attempt.executionId}
              onSelect={() => onSelect(attempt.executionId)}
              className={on ? "bg-accent-muted" : undefined}
            >
              <StatusIcon status={attempt.status} />
              <span className="min-w-8 whitespace-nowrap font-mono">{attempt.executionId}</span>
              <span className="min-w-0 flex-1 truncate">
                {[
                  MODE_WORD[attempt.mode] ?? attempt.mode,
                  clock(attempt.startedAt ?? attempt.createdAt),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              {tag ? <span className="text-label text-muted-foreground">{tag}</span> : null}
              {on ? <Check aria-hidden className="size-icon-sm" /> : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};
