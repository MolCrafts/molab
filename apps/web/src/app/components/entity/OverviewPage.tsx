import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { DashboardCard } from "./Dashboard";

interface OverviewPageProps {
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
}

export const OverviewPage = ({ children, aside, className }: OverviewPageProps): JSX.Element => {
  return (
    <div className={cn("flex-1 overflow-auto", className)}>
      <div
        className={cn(
          "grid min-h-full gap-x-8 gap-y-8 p-4 md:p-6",
          aside && "xl:grid-cols-(--overview-grid-columns)",
        )}
      >
        <div className="min-w-0 space-y-6">{children}</div>
        {aside && (
          <aside className="min-w-0 space-y-6 border-t border-border/60 pt-6 xl:border-l xl:border-t-0 xl:pl-8 xl:pt-0">
            {aside}
          </aside>
        )}
      </div>
    </div>
  );
};

interface OverviewSectionProps {
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Section on an overview. Renders `DashboardCard` so every tab shares one block. */
export const OverviewSection = ({
  title,
  description,
  children,
  className,
}: OverviewSectionProps): JSX.Element => (
  <DashboardCard title={title} className={className}>
    {description ? (
      <p className="mb-3 max-w-2xl text-body leading-relaxed text-muted-foreground">
        {description}
      </p>
    ) : null}
    {children}
  </DashboardCard>
);

interface OverviewHighlightProps {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}

export const OverviewHighlight = ({
  label,
  value,
  detail,
}: OverviewHighlightProps): JSX.Element => {
  return (
    <div className="border-l border-border/70 py-1 pl-3">
      <div className="text-label text-muted-foreground">{label}</div>
      <div className="mt-1 min-w-0 break-words text-heading font-semibold tracking-tight text-foreground">
        {value}
      </div>
      {detail && <div className="mt-1 text-label leading-5 text-muted-foreground">{detail}</div>}
    </div>
  );
};

interface OverviewHighlightGridProps {
  children: ReactNode;
}

export const OverviewHighlightGrid = ({ children }: OverviewHighlightGridProps): JSX.Element => {
  return <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2 xl:grid-cols-1">{children}</div>;
};
