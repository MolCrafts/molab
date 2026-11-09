// ─────────────────────────────────────────────────────────────────────────────
// The frame every overview gauge sits in. Not a card: a hairline rule above, a
// label on the rule, and a right-aligned readout carrying the one number the
// gauge is for. Composition — uneven columns, rows of different height — is
// the page's job; the frame stays out of the way so it can.
// ─────────────────────────────────────────────────────────────────────────────

import { type JSX, type ReactNode, useId } from "react";

import { cn } from "@/lib/utils";

interface GaugeProps {
  title: string;
  /** The number this gauge exists for, already phrased: "median 48m". */
  readout?: ReactNode;
  children: ReactNode;
  className?: string;
}

export const Gauge = ({ title, readout, children, className }: GaugeProps): JSX.Element => {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={cn("min-w-0 border-t border-border", className)}
    >
      <header className="flex min-w-0 items-baseline gap-3 pt-2 pb-2">
        <h3 id={headingId} className="shrink-0 text-label font-medium text-foreground">
          {title}
        </h3>
        {readout != null ? (
          <p className="ml-auto min-w-0 truncate text-right text-label text-muted-foreground">
            {readout}
          </p>
        ) : null}
      </header>
      {children}
    </section>
  );
};

/** A numeral inside a readout sentence. */
export const Figure = ({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}): JSX.Element => (
  <span className={cn("font-mono tabular-nums text-foreground", className)}>{children}</span>
);
