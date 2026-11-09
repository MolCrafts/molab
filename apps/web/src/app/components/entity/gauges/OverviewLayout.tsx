// ─────────────────────────────────────────────────────────────────────────────
// The frame every Overview tab shares: a canvas with a generous margin, one
// centred column with air between its sections, and a section heading that is
// a name on a hairline plus the one readout the section exists for. Air is the
// separator; nothing here draws a box.
// ─────────────────────────────────────────────────────────────────────────────

import { Sigma } from "lucide-react";
import type { JSX, ReactNode } from "react";
import type { StatusCounts } from "@/app/status/vocabulary";
import { FINISHED_GROUPS } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";
import { DashboardCanvas, OverviewSurface } from "../Dashboard";
import { StatusTally, Tally } from "./Glyph";

/** An Overview tab body: the scrolling surface, its margin, and the centred column. */
export const OverviewCanvas = ({ children }: { children: ReactNode }): JSX.Element => (
  <OverviewSurface>
    <DashboardCanvas className="px-4 py-6 sm:px-8 sm:py-8">
      <OverviewColumn>{children}</OverviewColumn>
    </DashboardCanvas>
  </OverviewSurface>
);

export const OverviewColumn = ({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}): JSX.Element => (
  <div className={cn("mx-auto w-full max-w-6xl space-y-12", className)}>{children}</div>
);

/** A chart's own heading: a name on a hairline, then the one readout it exists for. */
export const GaugeSection = ({
  title,
  readout,
  control,
  children,
}: {
  title: string;
  readout?: ReactNode;
  /** A small control beside the title, such as a choice of grouping. */
  control?: ReactNode;
  children: ReactNode;
}): JSX.Element => (
  <section aria-label={title} className="min-w-0">
    <header className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border/70 pb-2">
      <h2 className="text-label font-medium text-foreground">{title}</h2>
      {control}
      {readout != null ? (
        <p className="ml-auto min-w-0 truncate text-label text-muted-foreground">{readout}</p>
      ) : null}
    </header>
    <div className="pt-4">{children}</div>
  </section>
);

/** The success dial's key: each finished outcome as its icon and count, then Σ the basis. */
export const DialLegend = ({
  counts,
  unit = ["execution", "executions"],
  partial = false,
}: {
  counts: StatusCounts;
  unit?: readonly [string, string];
  partial?: boolean;
}): JSX.Element => {
  const finished = FINISHED_GROUPS.reduce((sum, id) => sum + counts[id], 0);
  const noun = finished === 1 ? unit[0] : unit[1];
  return (
    <div className="flex min-w-0 flex-col gap-2 text-label">
      {FINISHED_GROUPS.map((id) => (
        <StatusTally key={id} status={id} count={counts[id]} unit={unit[1]} />
      ))}
      <Tally
        icon={Sigma}
        value={partial ? `${finished}+` : finished}
        label={`${finished} finished ${noun}${partial ? ", loaded so far" : ""}`}
        className="border-t border-border/70 pt-1 text-muted-foreground"
      />
    </div>
  );
};

/** A pressed-button choice for a section's control slot. */
export const ChoiceToggle = <Value extends string>({
  label,
  value,
  choices,
  onChange,
}: {
  label: string;
  value: Value;
  choices: readonly { value: Value; label: string }[];
  onChange: (next: Value) => void;
}): JSX.Element => (
  // VS Code toggles: 22px, sans 12px words, the pressed one washed (L06 owner
  // feedback: the mono micro-text segment read "好丑").
  <fieldset aria-label={label} className="flex flex-wrap items-center gap-hairline">
    {choices.map((choice) => (
      <button
        key={choice.value}
        type="button"
        aria-pressed={choice.value === value}
        onClick={() => onChange(choice.value)}
        className={cn(
          "inline-flex h-shell-action items-center rounded-action px-2 text-label text-muted-foreground",
          "hover:bg-interactive hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          choice.value === value && "bg-interactive text-foreground",
        )}
      >
        {choice.label}
      </button>
    ))}
  </fieldset>
);
