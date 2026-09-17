/**
 * The selection being assembled, docked at the foot of the left panel.
 *
 * Grouping is the Project → Experiment → Run tree. A selected project or
 * experiment expands to the snapshot's children.
 */

import { ArrowUpRight, ChevronRight, GitCompare, Trash2, X } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type { WorkspaceSnapshot } from "@/app/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

import {
  type ComparisonExperimentNode,
  type ComparisonProjectNode,
  hydrateComparisonTree,
  keysUnderExperiment,
  keysUnderProject,
} from "./comparisonTree";
import { useCompareSet } from "./useCompareSet";

const INDENT = ["pl-1", "pl-4", "pl-7"] as const;

const Row = ({
  label,
  indent,
  open,
  expandable,
  onToggle,
  onRemove,
}: {
  label: string;
  indent: 0 | 1 | 2;
  open?: boolean;
  expandable?: boolean;
  onToggle?: () => void;
  onRemove?: () => void;
}): JSX.Element => (
  <div
    className={cn(
      "flex min-w-0 items-center gap-hairline rounded-hairline py-row-pad pr-1 hover:bg-muted/40",
      INDENT[indent],
    )}
  >
    {expandable ? (
      <WorkbenchIconAction
        label={open ? `Collapse ${label}` : `Expand ${label}`}
        className="size-control-compact flex-none"
        onClick={onToggle}
      >
        <ChevronRight className={cn("size-icon-sm transition-transform", open && "rotate-90")} />
      </WorkbenchIconAction>
    ) : (
      <span className="size-control-compact flex-none" />
    )}
    <span className="min-w-0 flex-1 truncate font-mono text-label text-foreground" title={label}>
      {label}
    </span>
    {onRemove ? (
      <WorkbenchIconAction
        label={`Remove ${label}`}
        className="size-control-compact flex-none"
        onClick={onRemove}
      >
        <X className="size-icon-sm" />
      </WorkbenchIconAction>
    ) : null}
  </div>
);

export const SelectionPanel = ({ snapshot }: { snapshot: WorkspaceSnapshot }): JSX.Element => {
  const { entries, count, remove, clear } = useCompareSet();
  const tree = useMemo(() => hydrateComparisonTree(entries, snapshot), [entries, snapshot]);
  const [open, setOpen] = useState<Set<string> | null>(null);

  const derivedOpen = useMemo(() => {
    const next = new Set<string>();
    for (const project of tree) {
      const hasBagRuns = project.experiments.some((experiment) =>
        experiment.runs.some((run) => !run.virtual),
      );
      if (hasBagRuns) next.add(project.id);
      for (const experiment of project.experiments) {
        if (experiment.runs.some((run) => !run.virtual)) next.add(experiment.id);
      }
    }
    return next;
  }, [tree]);
  const expanded = open ?? derivedOpen;

  const toggle = (id: string): void => {
    setOpen((current) => {
      const next = new Set(current ?? derivedOpen);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const removeAll = (keys: string[]): void => {
    for (const key of keys) remove(key);
  };

  return (
    <section
      className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden border-t border-border bg-surface"
      aria-label="Selection"
    >
      <header className="flex h-toolbar-compact shrink-0 items-center gap-1 px-2">
        <GitCompare className="size-icon-sm shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-label font-medium text-muted-foreground">
          Selection
        </span>
        <span className="shrink-0 font-mono text-micro text-muted-foreground tabular-nums">
          {count}
        </span>
        <WorkbenchIconAction label="Compare" kind={count > 0 ? "primary" : "ghost"} asChild>
          <Link to="/compare">
            <ArrowUpRight className="size-icon-sm" />
          </Link>
        </WorkbenchIconAction>
        <WorkbenchIconAction
          label="Remove every selected item"
          disabled={count === 0}
          onClick={clear}
        >
          <Trash2 className="size-icon-sm" />
        </WorkbenchIconAction>
      </header>

      {count === 0 ? null : (
        <ScrollArea className="min-h-0 min-w-0 flex-1">
          <div className="min-w-0 pb-2">
            {tree.map((project: ComparisonProjectNode) => (
              <div key={project.id} className="mb-1">
                <Row
                  label={project.name}
                  indent={0}
                  expandable={project.experiments.length > 0}
                  open={expanded.has(project.id)}
                  onToggle={() => toggle(project.id)}
                  onRemove={() => removeAll(keysUnderProject(entries, project))}
                />
                {expanded.has(project.id)
                  ? project.experiments.map((experiment: ComparisonExperimentNode) => (
                      <div key={experiment.id}>
                        <Row
                          label={experiment.name}
                          indent={1}
                          expandable={experiment.runs.length > 0}
                          open={expanded.has(experiment.id)}
                          onToggle={() => toggle(experiment.id)}
                          onRemove={
                            experiment.virtual
                              ? undefined
                              : () => removeAll(keysUnderExperiment(entries, project, experiment))
                          }
                        />
                        {expanded.has(experiment.id)
                          ? experiment.runs.map((run) => (
                              <Row
                                key={run.key}
                                label={run.entry.runName}
                                indent={2}
                                onRemove={run.virtual ? undefined : () => remove(run.key)}
                              />
                            ))
                          : null}
                      </div>
                    ))
                  : null}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </section>
  );
};
