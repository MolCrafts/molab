/**
 * One setting (L11, the VS Code Settings pattern): a semibold title, one line
 * of description, and its controls directly under it, left-aligned. A
 * category page is a stack of these under a `SettingsPageHeader`.
 *
 * Domain-free — no settings data lives here.
 */

import type { JSX, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface SettingItemProps {
  /** The setting's name; a search page passes `category` too. */
  title: ReactNode;
  /** "Category › " before the title (search results). */
  category?: string;
  /** Beside the title (an Active / Built in tag). */
  tag?: ReactNode;
  description?: ReactNode;
  /** Anchors a setting for links and search. */
  id?: string;
  /** The control(s), under the description. */
  children?: ReactNode;
  className?: string;
}

export const SettingItem = ({
  title,
  category,
  tag,
  description,
  id,
  children,
  className,
}: SettingItemProps): JSX.Element => (
  <section
    id={id}
    data-setting={id}
    className={cn("flex flex-col gap-1 border-b border-border py-3", className)}
  >
    <h3 className="flex min-w-0 flex-wrap items-center gap-2 text-body">
      {category ? <span className="text-muted-foreground">{category} ›</span> : null}
      <span className="font-semibold text-foreground">{title}</span>
      {tag}
    </h3>
    {description ? (
      <div className="text-label leading-relaxed text-muted-foreground">{description}</div>
    ) : null}
    {children ? <div className="flex flex-col gap-2 pt-1">{children}</div> : null}
  </section>
);

/** A small tag beside a setting's title. */
export const SettingTag = ({ children }: { children: ReactNode }): JSX.Element => (
  <span className="rounded-sm bg-accent-muted px-1 text-micro font-normal text-foreground">
    {children}
  </span>
);

/** The category page's head: its name and what it holds. */
export const SettingsPageHeader = ({
  title,
  description,
}: {
  title: string;
  description?: ReactNode;
}): JSX.Element => (
  <header className="flex flex-col gap-1 pt-1 pb-1">
    <h2 className="text-title font-semibold text-foreground">{title}</h2>
    {description ? <p className="text-label text-muted-foreground">{description}</p> : null}
  </header>
);

/** The buttons under a setting, in a row. */
export const SettingActions = ({ children }: { children: ReactNode }): JSX.Element => (
  <div className="flex flex-wrap items-center gap-2">{children}</div>
);
