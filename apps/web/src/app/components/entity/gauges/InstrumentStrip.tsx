// ─────────────────────────────────────────────────────────────────────────────
// Instrument strip — the row of gauges an Overview opens with. One band, not a
// row of cards: cells share a top and bottom rule and are divided by hairlines,
// so the eye reads across one panel. Each cell is a name, the one figure it
// exists for, and a face that draws that figure. A cell that has a detail tab
// behind it is itself the control that opens it.
// ─────────────────────────────────────────────────────────────────────────────

import { ArrowUpRight } from "lucide-react";
import { Children, type CSSProperties, type JSX, type ReactNode, useId } from "react";

import { cn } from "@/lib/utils";

export const InstrumentStrip = ({
  children,
  label,
  lead = true,
  className,
}: {
  children: ReactNode;
  label: string;
  /** The first cell carries a drawn dial and gets a wider column. */
  lead?: boolean;
  className?: string;
}): JSX.Element => {
  const count = Math.max(1, Children.toArray(children).length);
  // At the widest breakpoint every cell is one column; the strip never leaves a hole.
  const columns =
    count === 1 ? "1fr" : `${lead ? "1.4fr" : "1fr"} repeat(${count - 1}, minmax(0, 1fr))`;
  return (
    <section
      aria-label={label}
      style={{ "--strip-columns": columns } as CSSProperties}
      className={cn(
        "grid min-w-0 grid-cols-1 border-y border-border sm:grid-cols-2 xl:grid-cols-[var(--strip-columns)]",
        "[&>*]:border-border max-sm:[&>*+*]:border-t sm:max-xl:[&>*:nth-child(n+3)]:border-t",
        "sm:max-xl:[&>*:nth-child(even)]:border-l xl:[&>*+*]:border-l",
        className,
      )}
    >
      {children}
    </section>
  );
};

interface InstrumentProps {
  title: string;
  /** The figure, phrased: a numeral and its unit. Omit when the face carries it. */
  figure?: ReactNode;
  /** One quiet line under the figure — what the figure counts. */
  caption?: ReactNode;
  /** The drawn face. A figure-only cell (a count that opens its tab) may omit it. */
  children?: ReactNode;
  /** Opens the detail behind this gauge; names the action for assistive tech. */
  onSelect?: () => void;
  selectLabel?: string;
  /** Name of the tab the gauge opens, shown on hover of its arrow: "Timeline", "List". */
  selectHint?: string;
  /** Lay the face beside the figure instead of under it (the dial). */
  inline?: boolean;
  className?: string;
}

export const Instrument = ({
  title,
  figure,
  caption,
  children,
  onSelect,
  selectLabel,
  selectHint,
  inline = false,
  className,
}: InstrumentProps): JSX.Element => {
  const headingId = useId();
  const body = (
    <>
      <span className="flex min-w-0 items-center gap-2">
        <span id={headingId} className="truncate text-label font-medium text-foreground">
          {title}
        </span>
        {onSelect ? (
          <span
            aria-hidden
            title={selectHint}
            className="ml-auto flex shrink-0 items-center text-muted-foreground transition-colors group-hover:text-foreground group-focus-visible:text-foreground"
          >
            <ArrowUpRight className="size-icon" />
          </span>
        ) : null}
      </span>
      <span
        className={cn(
          "mt-3 flex min-w-0 flex-1",
          inline ? "items-center gap-4" : "flex-col justify-between gap-3",
        )}
      >
        {figure != null || caption != null ? (
          <span className="block min-w-0">
            {figure != null ? (
              <span className="block text-title font-semibold leading-tight tabular-nums text-foreground">
                {figure}
              </span>
            ) : null}
            {caption != null ? (
              <span className="block truncate text-label text-muted-foreground">{caption}</span>
            ) : null}
          </span>
        ) : null}
        {children != null ? (
          <span className={cn("block min-w-0", inline ? "flex-1" : "w-full")}>{children}</span>
        ) : null}
      </span>
    </>
  );
  const frame = "group flex min-w-0 flex-col px-6 py-6 text-left sm:min-h-40";
  if (onSelect) {
    return (
      <button
        type="button"
        aria-label={selectLabel}
        onClick={onSelect}
        className={cn(
          frame,
          "outline-none transition-colors hover:bg-interactive/50 focus-visible:bg-interactive/50 focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-inset",
          className,
        )}
      >
        {body}
      </button>
    );
  }
  return (
    <section aria-labelledby={headingId} className={cn(frame, className)}>
      {body}
    </section>
  );
};
