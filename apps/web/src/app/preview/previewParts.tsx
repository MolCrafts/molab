/** Level 2 / Level 3 pieces every Preview body is built from (L12). */

import type { JSX, ReactNode } from "react";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { CHART_GROUPS, type StatusCounts } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";

/**
 * The verdict line: glyph · status word · what it is about · the figure at the
 * right. A container passes `word={null}` and says its own line instead.
 */
export const PreviewVerdict = ({
  status,
  subject,
  right,
}: {
  /** Any status word (the vocabulary words and colours it), or none. */
  status: string | "none";
  subject?: ReactNode;
  right?: ReactNode;
}): JSX.Element => (
  // Icon OR text (retrofit R3): the glyph carries the status; the subject says what.
  <div className="flex min-w-0 items-center gap-2 text-title font-semibold">
    {status !== "none" ? <StatusIcon status={status} className="size-icon" /> : null}
    {subject ? <span className="min-w-0 truncate text-foreground">{subject}</span> : null}
    {right ? (
      <span className="ml-auto flex-none text-body font-normal tabular-nums text-muted-foreground">
        {right}
      </span>
    ) : null}
  </div>
);

/** Level 3: the one line of evidence, under the verdict's text column. */
export const PreviewEvidence = ({ children }: { children: ReactNode }): JSX.Element => (
  <p className="line-clamp-2 break-words pl-6 text-body text-muted-foreground">{children}</p>
);

/** Words that name the bar's colours — a key, not a tally (counts are in the tooltip). */
export const StatusWords = ({ counts }: { counts: StatusCounts }): JSX.Element => (
  <ul className="flex flex-wrap gap-x-3 gap-y-1 pl-6 text-label text-muted-foreground">
    {CHART_GROUPS.filter((group) => counts[group.id] > 0).map((group) => (
      <li key={group.id} className="flex items-center gap-1">
        <StatusIcon status={group.id} className="size-icon-sm" />
        {group.label.toLowerCase()}
      </li>
    ))}
  </ul>
);

/** A list row inside a Preview: glyph, a re-targeting name, a quiet figure. */
export const PreviewRow = ({
  status,
  children,
  figure,
  className,
}: {
  status?: string;
  children: ReactNode;
  figure?: ReactNode;
  className?: string;
}): JSX.Element => (
  <li className={cn("flex h-6 min-w-0 items-center gap-2", className)}>
    {status ? <StatusIcon status={status} className="size-icon-sm" /> : null}
    <span className="min-w-0 flex-1 truncate">{children}</span>
    {figure ? <span className="flex-none tabular-nums text-muted-foreground">{figure}</span> : null}
  </li>
);
