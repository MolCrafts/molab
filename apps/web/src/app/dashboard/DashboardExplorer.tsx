import { ArrowUpRight, Circle, FolderOpen } from "lucide-react";
import type { JSX } from "react";
import { Link } from "react-router-dom";

import { projectPath, runPath } from "@/app/entities/paths";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { runActivityAt, runPresentationStatus } from "@/app/runs/projections";
import { groupForStatus } from "@/app/runs/statusGroups";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

/** Sample size for the explorer shortcut. The heading count is the full set. */
export const RUNNING_FAILED_LIMIT = 3;
export const PROJECT_LIMIT = 6;

const activityValue = (run: WorkspaceRunRow): number => {
  const parsed = Date.parse(runActivityAt(run));
  return Number.isNaN(parsed) ? 0 : parsed;
};

/**
 * Running and failed runs, failed first, then newest activity.
 * This is a sample, not a user pin list.
 */
export const selectRunningAndFailed = (
  rows: readonly WorkspaceRunRow[],
): { visible: WorkspaceRunRow[]; total: number } => {
  const ranked = rows
    .filter((run) => {
      const group = groupForStatus(runPresentationStatus(run));
      return group === "running" || group === "failed";
    })
    .map((run) => ({
      run,
      failed: groupForStatus(runPresentationStatus(run)) === "failed",
      at: activityValue(run),
    }))
    .sort(
      (left, right) =>
        Number(right.failed) - Number(left.failed) ||
        right.at - left.at ||
        left.run.id.localeCompare(right.run.id),
    );
  return {
    visible: ranked.slice(0, RUNNING_FAILED_LIMIT).map(({ run }) => run),
    total: ranked.length,
  };
};

const moreLabel = (hidden: number, noun: "run" | "project"): string => {
  const word = hidden === 1 ? noun : `${noun}s`;
  return `View ${hidden} more ${word}`;
};

export const projectDetail = (
  summary: string,
  experimentCount: number | null | undefined,
): string => {
  if (summary) return summary;
  if (experimentCount == null) return "";
  if (experimentCount === 1) return "1 experiment";
  if (experimentCount === 0) return "No experiments yet";
  return `${experimentCount} experiments`;
};

const SectionLabel = ({ children, count }: { children: string; count: number }): JSX.Element => (
  <h3 className="flex items-baseline justify-between gap-2 px-1 pt-3 pb-1 text-label font-medium text-foreground">
    <span className="min-w-0 text-balance">{children}</span>
    <span className="shrink-0 tabular-nums text-muted-foreground">{count}</span>
  </h3>
);

const ExplorerLink = ({
  to,
  title,
  detail,
  tone,
}: {
  to: string;
  title: string;
  detail: string;
  tone?: "running" | "failed" | "default";
}): JSX.Element => (
  <Link
    to={to}
    className="group flex min-w-0 items-start gap-2 rounded-control px-1 py-row-pad outline-none hover:bg-interactive focus-visible:ring-1 focus-visible:ring-ring"
  >
    <Circle
      aria-hidden
      className={cn(
        "mt-1 size-2 shrink-0 fill-current",
        tone === "running"
          ? "text-status-running"
          : tone === "failed"
            ? "text-status-failed"
            : "text-muted-foreground/45",
      )}
    />
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
    <ArrowUpRight className="mt-1 size-3 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100" />
  </Link>
);

const MoreLink = ({ to, children }: { to: string; children: string }): JSX.Element => (
  <Link
    to={to}
    className="block min-w-0 truncate rounded-control px-1 py-1 text-label text-foreground outline-none hover:underline focus-visible:ring-1 focus-visible:ring-ring"
  >
    {children}
  </Link>
);

export const DashboardExplorer = ({ snapshot }: NavigationExplorerProps): JSX.Element => {
  const { rows } = useWorkspaceRuns();
  const runs = selectRunningAndFailed(rows);
  const hiddenRuns = runs.total - runs.visible.length;
  const projects = snapshot.projects.slice(0, PROJECT_LIMIT);
  const hiddenProjects = snapshot.projects.length - projects.length;

  const actions = (
    <WorkbenchIconAction label="Open projects" asChild>
      <Link to="/projects">
        <FolderOpen className="size-3.5" />
      </Link>
    </WorkbenchIconAction>
  );

  return (
    <LeftExplorer title="Workspace" actions={actions}>
      <div className="space-y-1">
        {runs.total > 0 ? (
          <>
            <SectionLabel count={runs.total}>Running and failed</SectionLabel>
            {runs.visible.map((run) => {
              const group = groupForStatus(runPresentationStatus(run));
              const statusWord = group === "running" ? "Running" : "Failed";
              return (
                <ExplorerLink
                  key={`${run.workspaceKey}:${run.id}`}
                  to={runPath(run.projectId, run.experimentId, run.id)}
                  title={run.name || run.id}
                  detail={[statusWord, run.experimentName].filter(Boolean).join(" · ")}
                  tone={group === "running" ? "running" : "failed"}
                />
              );
            })}
            {hiddenRuns > 0 ? <MoreLink to="/runs">{moreLabel(hiddenRuns, "run")}</MoreLink> : null}
          </>
        ) : null}

        <SectionLabel count={snapshot.projects.length}>Projects</SectionLabel>
        {projects.length === 0 ? (
          <p className="px-1 text-label text-muted-foreground">No projects yet.</p>
        ) : (
          projects.map((project) => (
            <ExplorerLink
              key={project.id}
              to={projectPath(project.id)}
              title={project.name}
              detail={projectDetail(project.summary, project.experimentCount)}
            />
          ))
        )}
        {hiddenProjects > 0 ? (
          <MoreLink to="/projects">{moreLabel(hiddenProjects, "project")}</MoreLink>
        ) : null}
      </div>
    </LeftExplorer>
  );
};
