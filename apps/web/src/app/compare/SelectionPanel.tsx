/**
 * The selection being assembled, docked at the foot of the left panel.
 *
 * Rows are the bag, grouped by category (an empty category is Ungrouped).
 * Move up / Move down reorder that bag. The hydrated project tree supplies
 * display names when the snapshot knows the entity.
 */

import { ArrowUpRight, ChevronDown, ChevronUp, GitCompare, Trash2 } from "lucide-react";
import { type JSX, useMemo } from "react";
import { Link } from "react-router-dom";

import type { WorkspaceSnapshot } from "@/app/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { WorkbenchIconAction } from "@/components/workbench";

import { buildCategoryGroups, hydrateComparisonTree } from "./comparisonTree";
import { type CompareItem, itemKey } from "./types";
import { compareSet, reorderItems, setItemCategory, useCompareSet } from "./useCompareSet";

const entryLabel = (entry: CompareItem, tree: ReturnType<typeof hydrateComparisonTree>): string => {
  const project = tree.find(
    (node) =>
      node.workspaceKey === entry.ref.workspaceKey && node.projectId === entry.ref.projectId,
  );
  if (entry.ref.kind === "project")
    return project?.name || entry.projectName || entry.ref.projectId;
  if (entry.ref.kind === "experiment") {
    const experimentId = entry.ref.experimentId;
    const experiment = project?.experiments.find((node) => node.experimentId === experimentId);
    return experiment?.name || entry.experimentName || experimentId;
  }
  return entry.runName || entry.ref.runId;
};

const assignCategory = (entries: readonly CompareItem[], key: string, raw: string): void => {
  const trimmed = raw.trim();
  compareSet.replace(setItemCategory(entries, key, trimmed.length === 0 ? null : trimmed));
};

export const SelectionPanel = ({ snapshot }: { snapshot: WorkspaceSnapshot }): JSX.Element => {
  const { entries, count, remove, clear } = useCompareSet();
  const tree = useMemo(() => hydrateComparisonTree(entries, snapshot), [entries, snapshot]);
  const groups = useMemo(() => buildCategoryGroups(entries), [entries]);

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
          <div className="min-w-0 space-y-2 pb-2">
            {groups.map((group) => (
              <div key={group.category ?? ""}>
                <p className="px-2 pt-1 font-mono text-micro text-muted-foreground">
                  {group.category ?? "Ungrouped"}
                </p>
                {group.items.map((entry) => {
                  const key = itemKey(entry.ref);
                  const index = entries.findIndex((item) => itemKey(item.ref) === key);
                  const label = entryLabel(entry, tree);
                  return (
                    <div
                      key={key}
                      className="flex min-w-0 items-center gap-hairline px-1 py-row-pad"
                    >
                      <WorkbenchIconAction
                        label="Move up"
                        disabled={index <= 0}
                        onClick={() => compareSet.replace(reorderItems(entries, index, index - 1))}
                      >
                        <ChevronUp className="size-icon-sm" />
                      </WorkbenchIconAction>
                      <WorkbenchIconAction
                        label="Move down"
                        disabled={index < 0 || index >= entries.length - 1}
                        onClick={() => compareSet.replace(reorderItems(entries, index, index + 1))}
                      >
                        <ChevronDown className="size-icon-sm" />
                      </WorkbenchIconAction>
                      <span className="min-w-0 flex-1 truncate font-mono text-label" title={label}>
                        {label}
                      </span>
                      <input
                        aria-label={`Category for ${label}`}
                        defaultValue={entry.category ?? ""}
                        key={`${key}:${entry.category ?? ""}`}
                        placeholder="Category"
                        className="h-control-compact w-16 rounded-control border border-border bg-transparent px-1 font-mono text-micro"
                        onBlur={(event) => assignCategory(entries, key, event.target.value)}
                      />
                      <WorkbenchIconAction label={`Remove ${label}`} onClick={() => remove(key)}>
                        <Trash2 className="size-icon-sm" />
                      </WorkbenchIconAction>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </section>
  );
};
