/**
 * The shared chrome of a `<molab-…>` component (L10): a white box with a
 * hairline border on the page tint, an optional footer line, and the states
 * every component shares (loading, a reference that does not resolve, a bad
 * attribute). Components never invent their own box.
 */

import type { JSX, ReactNode } from "react";
import { cn } from "@/lib/utils";

export const ComponentFrame = ({
  children,
  footer,
  className,
  label,
}: {
  children: ReactNode;
  /** A muted line under the content (source, "live", an ↗). */
  footer?: ReactNode;
  className?: string;
  /** Accessible name of the block. */
  label?: string;
}): JSX.Element => (
  <section
    aria-label={label}
    className={cn(
      "not-prose overflow-hidden rounded-control border border-border bg-surface text-body",
      className,
    )}
  >
    {children}
    {footer ? (
      <div className="flex h-6 items-center gap-2 border-t border-border px-3 text-label text-muted-foreground">
        {footer}
      </div>
    ) : null}
  </section>
);

/** A component that cannot draw: its name and why, in one muted line. */
export const ComponentNotice = ({
  name,
  children,
}: {
  name: string;
  children: ReactNode;
}): JSX.Element => (
  <div
    role="note"
    className="not-prose flex items-center gap-2 rounded-control border border-dashed border-border px-3 py-2 text-label text-muted-foreground"
  >
    <span className="font-mono">&lt;{name}&gt;</span>
    <span>{children}</span>
  </div>
);

/** Loading placeholder sized like one row. */
export const ComponentLoading = ({ name }: { name: string }): JSX.Element => (
  <ComponentNotice name={name}>Loading…</ComponentNotice>
);
