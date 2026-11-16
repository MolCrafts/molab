/**
 * An editor view's label — icon OR text (owner rule, retrofit R1 / R2):
 * on a desktop the tab is the word and, for a list, its count (VS Code panel
 * tabs); on a phone the bottom bar is the icon alone, the word kept for
 * assistive tech and the tooltip.
 */

import type { ComponentType, JSX } from "react";

export const ViewLabel = ({
  icon: Icon,
  children,
  count,
  dirty,
}: {
  icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  children: string;
  count?: number;
  /** The view holds unsaved edits (L06): a ● after the word, as VS Code marks a file. */
  dirty?: boolean;
}): JSX.Element => (
  <>
    <Icon aria-hidden className="size-5 sm:hidden" />
    <span className="max-sm:sr-only" title={children}>
      {children}
    </span>
    {dirty ? (
      <span role="img" aria-label="unsaved" className="ml-1 size-2 rounded-full bg-foreground" />
    ) : null}
    {count ? (
      <span className="ml-1 min-w-4 rounded-full bg-muted px-1 text-center text-micro tabular-nums text-muted-foreground max-sm:hidden">
        {count}
      </span>
    ) : null}
  </>
);
