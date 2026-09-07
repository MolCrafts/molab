/**
 * The comparison being assembled, docked at the foot of the left panel.
 *
 * Gathering runs to compare means walking between projects — and between
 * sections, since a run is as easily opened from Projects or Files as from the
 * Runs table. So it is part of the panel itself rather than one explorer's
 * footer: it is present wherever the user currently is, and it outlives the
 * table they ticked runs in. It stays on screen when empty, too, because a
 * staging area that only appears once something is in it cannot tell anyone
 * that staging is possible.
 *
 * The panel is the set, not the charts: the comparison itself is a page, and
 * the header carries the one link to it — otherwise the only way to the runs
 * you just gathered is to remember which section holds the tab they are
 * drawn in.
 *
 * Structure is the ancestry: project → experiment → run. A comparison spanning
 * three projects is unreadable as a flat list of parameter slugs, and nesting
 * says which is which without spending label width on it.
 *
 * Membership and selection are separate: a run stays staged while it is
 * toggled in and out of the chart, so narrowing twenty runs to three does not
 * throw the other seventeen away. Ticking a project or an experiment is the
 * same toggle applied to everything under it.
 */

import { ArrowUpRight, ChevronRight, GitCompare, ListChecks, Trash2, X } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { runsTabPath } from "@/app/runs/RunsTabBar";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

import {
  buildComparisonTree,
  type ComparisonRunNode,
  comparisonSpansWorkspaces,
  type GroupCheckState,
  groupCheckState,
  runsOfProject,
} from "./comparisonTree";
import { useCompareSet } from "./useCompareSet";

const INDENT = 12;

const checkedProp = (state: GroupCheckState): boolean | "indeterminate" =>
  state === "indeterminate" ? "indeterminate" : state === "checked";

interface GroupRowProps {
  depth: number;
  label: string;
  hint?: string;
  count: number;
  state: GroupCheckState;
  expanded: boolean;
  onToggleExpanded: () => void;
  onToggleChecked: () => void;
}

const GroupRow = ({
  depth,
  label,
  hint,
  count,
  state,
  expanded,
  onToggleExpanded,
  onToggleChecked,
}: GroupRowProps): JSX.Element => (
  <div
    className="flex h-control-compact items-center gap-1 rounded-[2px] pr-1 hover:bg-muted/40"
    style={{ paddingLeft: `${depth * INDENT}px` }}
  >
    <WorkbenchIconAction
      label={expanded ? `Collapse ${label}` : `Expand ${label}`}
      className="size-5 flex-none text-muted-foreground"
      onClick={onToggleExpanded}
    >
      <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-90")} />
    </WorkbenchIconAction>
    <Checkbox
      checked={checkedProp(state)}
      aria-label={`Include every run under ${label} in the comparison`}
      onCheckedChange={onToggleChecked}
    />
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="min-w-0 flex-1 truncate bg-transparent px-0 text-left text-label font-medium text-foreground"
          onClick={onToggleExpanded}
        >
          {label}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" className="max-w-md">
        <span className="font-mono text-micro">{hint ?? label}</span>
      </TooltipContent>
    </Tooltip>
    <span className="flex-none font-mono text-micro text-muted-foreground tabular-nums">
      {count}
    </span>
  </div>
);

interface RunRowProps {
  node: ComparisonRunNode;
  depth: number;
  onToggle: (key: string, selected: boolean) => void;
  onRemove: (key: string) => void;
}

const RunRow = ({ node, depth, onToggle, onRemove }: RunRowProps): JSX.Element => {
  const { entry } = node;
  return (
    <div
      className="group flex h-control-compact items-center gap-1 rounded-[2px] pr-1 hover:bg-muted/40"
      style={{ paddingLeft: `${depth * INDENT + 20}px` }}
    >
      <Checkbox
        checked={entry.selected}
        aria-label={`Include ${entry.runName} in the comparison`}
        onCheckedChange={(next) => onToggle(node.key, next === true)}
      />
      {/* The row shows only the run's own name — its ancestry is the nesting
          above it — so the full path has to be reachable on hover. */}
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="min-w-0 flex-1 truncate font-mono text-label text-muted-foreground">
            {entry.runName}
          </span>
        </TooltipTrigger>
        <TooltipContent side="right" className="max-w-md">
          <span className="font-mono text-micro">
            {entry.workspaceLabel} / {entry.projectName} / {entry.experimentName} / {entry.runName}
            {entry.executionId ? ` / ${entry.executionId}` : ""}
          </span>
        </TooltipContent>
      </Tooltip>
      <WorkbenchIconAction
        label={`Remove ${entry.runName} from the comparison`}
        className="size-5 flex-none opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
        onClick={() => onRemove(node.key)}
      >
        <X className="h-3 w-3" />
      </WorkbenchIconAction>
    </div>
  );
};

export const ComparisonPanel = (): JSX.Element => {
  const { entries, selected, count, remove, clear, setSelected, setManySelected, setAllSelected } =
    useCompareSet();
  // Collapsed rather than expanded, so a project staged after the panel was
  // first rendered arrives open — the run that was just added is the one the
  // user wants to see.
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set<string>());

  const tree = useMemo(() => buildComparisonTree(entries), [entries]);
  const showWorkspace = useMemo(() => comparisonSpansWorkspaces(entries), [entries]);
  const allOn = count > 0 && selected.length === count;

  const toggleCollapsed = (id: string): void => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  };

  const setGroupSelected = (runs: readonly ComparisonRunNode[], next: boolean): void => {
    setManySelected(new Set(runs.map((run) => run.key)), next);
  };

  return (
    <section
      className="flex h-full min-h-0 flex-col border-t border-border bg-surface"
      aria-label="Comparison"
    >
      <header className="flex h-[28px] shrink-0 items-center gap-1 px-2">
        <GitCompare className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate font-semibold text-label text-muted-foreground uppercase tracking-wide">
          Comparison
        </span>
        <span className="shrink-0 font-mono text-micro text-muted-foreground tabular-nums">
          {selected.length}/{count}
        </span>
        {/* The set lives here; the charts live on a page. Without this the
            page is only reachable by recalling which section owns the tab. */}
        <WorkbenchIconAction label="Open the comparison" asChild>
          <Link to={runsTabPath("compare")}>
            <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </WorkbenchIconAction>
        <WorkbenchIconAction
          label={allOn ? "Untick every staged run" : "Tick every staged run"}
          className="size-5"
          disabled={count === 0}
          onClick={() => setAllSelected(!allOn)}
        >
          <ListChecks className={cn("h-3.5 w-3.5", allOn && "text-accent")} />
        </WorkbenchIconAction>
        <WorkbenchIconAction
          label="Remove every staged run"
          className="size-5"
          disabled={count === 0}
          onClick={clear}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </WorkbenchIconAction>
      </header>

      {count === 0 ? (
        <p className="px-2 pb-2 text-micro text-muted-foreground">
          Tick runs in the Runs table to stage them here. The comparison follows you across projects
          and workspaces.
        </p>
      ) : (
        <ScrollArea className="min-h-0 flex-1">
          <div className="px-1 pb-1.5">
            {tree.map((project) => {
              const projectRuns = runsOfProject(project);
              const projectOpen = !collapsed.has(project.id);
              return (
                <div key={project.id}>
                  <GroupRow
                    depth={0}
                    label={
                      showWorkspace ? `${project.workspaceLabel} / ${project.name}` : project.name
                    }
                    hint={`${project.workspaceLabel} / ${project.name}`}
                    count={projectRuns.length}
                    state={groupCheckState(projectRuns)}
                    expanded={projectOpen}
                    onToggleExpanded={() => toggleCollapsed(project.id)}
                    onToggleChecked={() =>
                      setGroupSelected(projectRuns, groupCheckState(projectRuns) !== "checked")
                    }
                  />
                  {projectOpen &&
                    project.experiments.map((experiment) => {
                      const experimentOpen = !collapsed.has(experiment.id);
                      return (
                        <div key={experiment.id}>
                          <GroupRow
                            depth={1}
                            label={experiment.name}
                            count={experiment.runs.length}
                            state={groupCheckState(experiment.runs)}
                            expanded={experimentOpen}
                            onToggleExpanded={() => toggleCollapsed(experiment.id)}
                            onToggleChecked={() =>
                              setGroupSelected(
                                experiment.runs,
                                groupCheckState(experiment.runs) !== "checked",
                              )
                            }
                          />
                          {experimentOpen &&
                            experiment.runs.map((run) => (
                              <RunRow
                                key={run.key}
                                node={run}
                                depth={2}
                                onToggle={setSelected}
                                onRemove={remove}
                              />
                            ))}
                        </div>
                      );
                    })}
                </div>
              );
            })}
          </div>
        </ScrollArea>
      )}
    </section>
  );
};
