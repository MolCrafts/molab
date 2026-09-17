import { ArrowUpRight, Circle, Plus } from "lucide-react";
import type { JSX } from "react";
import { Link } from "react-router-dom";

import { runPath } from "@/app/entities/paths";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { runPresentationStatus } from "@/app/runs/projections";
import { groupForStatus } from "@/app/runs/statusGroups";
import { useWorkspaceRuns } from "@/app/runs/useWorkspaceRuns";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

const SectionLabel = ({ children }: { children: string }): JSX.Element => (
  <h3 className="px-1 pb-1 pt-3 text-micro font-medium uppercase tracking-wide text-muted-foreground">
    {children}
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
      <span className="block truncate text-label font-medium text-foreground">{title}</span>
      <span className="block truncate text-micro text-muted-foreground">{detail}</span>
    </span>
    <ArrowUpRight className="mt-1 size-3 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100" />
  </Link>
);

export const DashboardExplorer = ({ snapshot }: NavigationExplorerProps): JSX.Element => {
  const { rows } = useWorkspaceRuns();
  const activeWorkspace = snapshot.workspaces.find((workspace) => workspace.active) ??
    snapshot.workspaces[0] ?? { label: "Workspace", unreachable: false, isRemote: false };
  const pinnedRuns = rows
    .filter((run) => {
      const group = groupForStatus(runPresentationStatus(run));
      return group === "running" || group === "failed";
    })
    .slice(0, 3);

  const actions = (
    <WorkbenchIconAction label="Open projects" asChild>
      <Link to="/projects">
        <Plus className="size-3.5" />
      </Link>
    </WorkbenchIconAction>
  );

  return (
    <LeftExplorer title="Workspace" actions={actions}>
      <div className="space-y-1">
        <div className="border-b border-border/70 px-1 pb-2">
          <p className="truncate text-label font-medium text-foreground">{activeWorkspace.label}</p>
          <p
            className={cn(
              "mt-1 flex items-center gap-2 text-micro",
              activeWorkspace.unreachable
                ? "text-status-failed-foreground"
                : "text-status-completed-foreground",
            )}
          >
            <span className="size-1.5 rounded-full bg-current" aria-hidden />
            {activeWorkspace.isRemote ? "Remote workspace" : "Local workspace"} ·{" "}
            {activeWorkspace.unreachable ? "unavailable" : "connected"}
          </p>
        </div>

        {pinnedRuns.length > 0 ? (
          <>
            <SectionLabel>Pinned</SectionLabel>
            {pinnedRuns.map((run) => {
              const group = groupForStatus(runPresentationStatus(run));
              return (
                <ExplorerLink
                  key={run.id}
                  to={runPath(run.projectId, run.experimentId, run.id)}
                  title={run.name || run.id}
                  detail={run.experimentName}
                  tone={group === "running" ? "running" : group === "failed" ? "failed" : "default"}
                />
              );
            })}
          </>
        ) : null}

        <SectionLabel>Projects</SectionLabel>
        {snapshot.projects.slice(0, 6).map((project) => (
          <ExplorerLink
            key={project.id}
            to={`/projects/${encodeURIComponent(project.id)}`}
            title={project.name}
            detail={project.summary || `${project.experimentCount ?? 0} experiments`}
          />
        ))}
      </div>
    </LeftExplorer>
  );
};
