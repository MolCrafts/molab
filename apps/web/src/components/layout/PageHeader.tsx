/**
 * Page header — one title and one action cluster for a work surface.
 *
 * Domain-free block. Products decide the icon, title, and actions; this block
 * keeps title hierarchy and toolbar geometry consistent without adding cards.
 */

import type { ComponentType, JSX, ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  icon?: ComponentType<{ className?: string }>;
  title: string;
  titleTooltip?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  icon: Icon,
  title,
  titleTooltip,
  actions,
  className,
}: PageHeaderProps): JSX.Element {
  return (
    <header className={cn("bg-surface", className)} data-slot="page-header">
      <div className="flex h-toolbar min-w-0 items-center gap-2 px-2">
        {Icon ? (
          <div className="hidden size-7 flex-none items-center justify-center text-accent sm:flex">
            <Icon className="size-icon" aria-hidden />
          </div>
        ) : null}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <h1
            className="truncate text-title font-semibold tracking-tight text-foreground"
            title={titleTooltip ?? title}
          >
            {title}
          </h1>
        </div>
        {actions ? <div className="flex flex-none items-center gap-hairline">{actions}</div> : null}
      </div>
    </header>
  );
}
