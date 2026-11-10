// Breadcrumb row (L00): 22px under the editor tabs — project › experiment ›
// run › attempt, names only, each ancestor a link. A single segment still
// renders: a project page is one name, and that name is the trail.
// Driven by ``buildTrail`` from the active editor; it lives once in the shell.

import { ChevronRight } from "lucide-react";
import { Fragment, type JSX } from "react";
import { Link } from "react-router-dom";
import type { BreadcrumbItem } from "@/app/types";
import { cn } from "@/lib/utils";

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export const Breadcrumb = ({ items }: BreadcrumbProps): JSX.Element | null => {
  if (items.length === 0) return null;
  return (
    <nav
      aria-label="Breadcrumb"
      className="box-content flex h-shell-crumbs min-w-0 flex-none items-center gap-hairline overflow-hidden bg-background px-6 pt-1 text-label text-muted-foreground"
    >
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        const body = <span className="truncate">{item.label}</span>;
        return (
          <Fragment key={`${item.kind}:${item.label}`}>
            {index > 0 && (
              <ChevronRight className="size-icon-sm flex-none opacity-60" aria-hidden />
            )}
            {item.to ? (
              <Link
                to={item.to}
                title={item.label}
                aria-current={isLast ? "page" : undefined}
                className="flex min-w-0 items-center gap-1 rounded-hairline px-1 hover:bg-interactive hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {body}
              </Link>
            ) : (
              <span
                title={item.label}
                aria-current={isLast ? "page" : undefined}
                className={cn("flex min-w-0 items-center gap-1 px-1", isLast && "text-foreground")}
              >
                {body}
              </span>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
};
