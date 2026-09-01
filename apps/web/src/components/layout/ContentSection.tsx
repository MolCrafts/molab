/**
 * Content section — semantic page grouping without card chrome.
 *
 * Domain-free block for operational pages, inventories, and detail overviews.
 * Products own the content and actions; this block owns heading association,
 * spacing, and the shared hierarchy between title, description, and body.
 */

import { type JSX, type ReactNode, useId } from "react";
import { cn } from "@/lib/utils";

export interface ContentSectionProps {
  id?: string;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}

export function ContentSection({
  id,
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
}: ContentSectionProps): JSX.Element {
  const generatedId = useId();
  const headingId = id ? `${id}-heading` : `content-section-${generatedId}`;

  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn("space-y-3", className)}
      data-slot="content-section"
    >
      <header className="flex min-w-0 items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h2 id={headingId} className="text-body-lg font-semibold tracking-tight text-foreground">
            {title}
          </h2>
          {description ? <p className="text-label text-muted-foreground">{description}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </header>
      <div className={cn("min-w-0", bodyClassName)}>{children}</div>
    </section>
  );
}
