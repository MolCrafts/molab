import { ListTodo, PanelsTopLeft } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  type DashboardAttentionItem,
  type DashboardAttentionOverflow,
  type DashboardRecentItem,
  runActivityTimestamp,
} from "@/app/dashboard/dashboardModel";
import { runPath } from "@/app/entities/paths";
import { runPresentationStatus } from "@/app/runs/projections";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { RunStatusBadge, WorkbenchIconAction } from "@/components/workbench";
import { formatRelative } from "@/lib/format-time";

interface DashboardTriageProps {
  failed: readonly DashboardAttentionItem[];
  failedOverflow: DashboardAttentionOverflow | null;
  activeRuns: readonly WorkspaceRunRow[];
  hiddenActiveCount: number;
  recentItems: readonly DashboardRecentItem[];
  showEmpty: boolean;
}

const relativeLabel = (iso: string): string => {
  if (!iso || Number.isNaN(Date.parse(iso))) return "";
  return formatRelative(iso);
};

const TriageSection = ({
  id,
  title,
  children,
  footer,
}: {
  id: string;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}): JSX.Element => (
  <section aria-labelledby={id}>
    <h2 id={id} className="text-balance px-4 pt-6 pb-1 text-title font-medium text-foreground">
      {title}
    </h2>
    <ul className="divide-y divide-border/60">{children}</ul>
    {footer}
  </section>
);

const TriageRow = ({
  href,
  title,
  detail,
  meta,
  marker,
}: {
  href: string;
  title: string;
  detail: string;
  meta: string;
  marker: ReactNode;
}): JSX.Element => (
  <li>
    <Link
      to={href}
      className="flex min-w-0 items-center gap-3 px-4 py-3 hover:bg-muted/40 focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none focus-visible:ring-inset"
    >
      <span className="shrink-0">{marker}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-body font-medium text-foreground" title={title}>
          {title}
        </span>
        {detail ? (
          <span className="block truncate text-label text-muted-foreground" title={detail}>
            {detail}
          </span>
        ) : null}
      </span>
      {meta ? <span className="shrink-0 text-label text-muted-foreground">{meta}</span> : null}
    </Link>
  </li>
);

const MoreLink = ({ href, label }: { href: string; label: string }): JSX.Element => (
  <p className="px-4 py-2 text-label">
    <Link
      to={href}
      className="rounded-control text-foreground underline-offset-2 outline-none hover:underline focus-visible:ring-1 focus-visible:ring-ring"
    >
      {label}
    </Link>
  </p>
);

const countedMore = (label: string, singular: string, plural: string): string =>
  `${label} ${label === "View 1 more" ? singular : plural}`;

/**
 * The landing triage: failed runs, work in progress, and recent items.
 * Charts stay off this list.
 */
export const DashboardTriage = ({
  failed,
  failedOverflow,
  activeRuns,
  hiddenActiveCount,
  recentItems,
  showEmpty,
}: DashboardTriageProps): JSX.Element | null => {
  if (showEmpty) {
    return (
      <div className="px-4 py-8">
        <p className="max-w-[65ch] text-body text-foreground">
          No projects or runs in this workspace yet.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <WorkbenchIconAction label="Open projects" asChild>
            <Link to="/projects">
              <PanelsTopLeft aria-hidden />
            </Link>
          </WorkbenchIconAction>
          <WorkbenchIconAction label="Open runs" asChild>
            <Link to="/runs">
              <ListTodo aria-hidden />
            </Link>
          </WorkbenchIconAction>
        </div>
      </div>
    );
  }

  return (
    <>
      {failed.length > 0 ? (
        <TriageSection
          id="dashboard-needs-attention"
          title="Needs attention"
          footer={
            failedOverflow?.href ? (
              <MoreLink
                href={failedOverflow.href}
                label={countedMore(failedOverflow.label, "failed run", "failed runs")}
              />
            ) : failedOverflow ? (
              <p className="px-4 py-2 text-label text-muted-foreground">
                {countedMore(failedOverflow.label, "failed run", "failed runs")}
              </p>
            ) : null
          }
        >
          {failed.map((item) => (
            <TriageRow
              key={item.id}
              href={item.href ?? "/runs"}
              title={item.title}
              detail={item.detail}
              meta=""
              marker={<RunStatusBadge status="failed" size="md" />}
            />
          ))}
        </TriageSection>
      ) : null}
      {activeRuns.length > 0 ? (
        <TriageSection
          id="dashboard-in-progress"
          title="In progress"
          footer={
            hiddenActiveCount > 0 ? (
              <MoreLink
                href="/runs"
                label={`View ${hiddenActiveCount} more ${hiddenActiveCount === 1 ? "run" : "runs"}`}
              />
            ) : null
          }
        >
          {activeRuns.map((run) => (
            <TriageRow
              key={`${run.workspaceKey}:${run.id}`}
              href={runPath(run.projectId, run.experimentId, run.id)}
              title={run.name || run.id}
              detail={`${run.projectName} · ${run.experimentName}`}
              meta={relativeLabel(runActivityTimestamp(run))}
              marker={<RunStatusBadge status={runPresentationStatus(run)} size="md" />}
            />
          ))}
        </TriageSection>
      ) : null}
      {recentItems.length > 0 ? (
        <TriageSection id="dashboard-recent" title="Recent">
          {recentItems.map((item) => (
            <TriageRow
              key={item.id}
              href={item.href}
              title={item.title}
              detail={item.detail}
              meta={relativeLabel(item.timestamp)}
              marker={
                item.status ? (
                  <RunStatusBadge status={item.status} size="md" />
                ) : (
                  <span className="text-label text-muted-foreground">{item.type}</span>
                )
              }
            />
          ))}
        </TriageSection>
      ) : null}
    </>
  );
};
