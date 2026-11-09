/**
 * The selection being assembled: the Pinned section at the foot of the side bar.
 *
 * Rows are the bag, grouped by category (an empty category is Ungrouped).
 * Move up / Move down reorder that bag. The hydrated project tree supplies
 * display names when the snapshot knows the entity.
 */

import { ArrowUpRight, ChevronDown, ChevronRight, ListX, X } from "lucide-react";
import { type JSX, useMemo } from "react";
import { Link } from "react-router-dom";

import type { WorkspaceSnapshot } from "@/app/types";
import { WorkbenchIconAction } from "@/components/workbench";

import { hydrateComparisonTree } from "./comparisonTree";
import { compareEntriesForWorkspaces } from "./servedSelection";
import { type CompareItem, itemKey } from "./types";
import { useCompareSet } from "./useCompareSet";

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

export interface SelectionPanelProps {
  snapshot: WorkspaceSnapshot;
  /** Collapsed by default (L00): only the section header shows. */
  expanded: boolean;
  onToggle: () => void;
}

/**
 * The side bar's **Pinned** section (L00, formerly the compare dock): a
 * VS Code section header — chevron, caps title, count, actions — over the bag.
 */
export const SelectionPanel = ({
  snapshot,
  expanded,
  onToggle,
}: SelectionPanelProps): JSX.Element => {
  const { entries, remove, clear } = useCompareSet();
  const visible = compareEntriesForWorkspaces(
    entries,
    snapshot.workspaces.map((workspace) => workspace.key),
  );
  const tree = useMemo(() => hydrateComparisonTree(visible, snapshot), [visible, snapshot]);
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <section
      className="flex h-full min-h-0 flex-col overflow-hidden border-t border-border"
      aria-label="Pinned"
    >
      <div className="group flex h-shell-row flex-none items-center gap-1 pr-1">
        <button
          type="button"
          className="flex h-full min-w-0 flex-1 items-center gap-1 pl-1 text-left outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-ring"
          aria-expanded={expanded}
          onClick={onToggle}
        >
          <Chevron className="size-icon flex-none text-foreground" aria-hidden />
          <span className="truncate text-micro font-semibold uppercase tracking-wide text-foreground">
            Pinned
          </span>
        </button>
        {visible.length > 0 ? (
          <>
            <WorkbenchIconAction
              size="shell"
              label="Compare pinned runs"
              className="hidden group-focus-within:inline-flex group-hover:inline-flex"
              asChild
            >
              <Link to="/compare">
                <ArrowUpRight aria-hidden />
              </Link>
            </WorkbenchIconAction>
            <WorkbenchIconAction
              size="shell"
              label="Clear pinned"
              className="hidden group-focus-within:inline-flex group-hover:inline-flex"
              onClick={clear}
            >
              <ListX aria-hidden />
            </WorkbenchIconAction>
            <span className="min-w-4 rounded-full bg-muted px-1 text-center font-mono text-micro tabular-nums text-muted-foreground">
              {visible.length}
            </span>
          </>
        ) : null}
      </div>
      {expanded ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-1">
          {visible.length === 0 ? (
            <p className="px-2 py-1 text-label text-muted-foreground">
              Nothing pinned. Use Add to selection on a run, the tree or a runs table.
            </p>
          ) : (
            <ul>
              {visible.map((entry) => {
                const key = itemKey(entry.ref);
                const label = entryLabel(entry, tree);
                return (
                  <li
                    key={key}
                    className="group/row flex h-shell-row min-w-0 items-center gap-1 pl-4"
                  >
                    <span className="min-w-0 flex-1 truncate text-body" title={label}>
                      {label}
                      {entry.category ? (
                        <span className="ml-1 font-mono text-micro text-muted-foreground">
                          {entry.category}
                        </span>
                      ) : null}
                    </span>
                    <WorkbenchIconAction
                      size="shell"
                      label={`Unpin ${label}`}
                      className="invisible group-focus-within/row:visible group-hover/row:visible"
                      onClick={() => remove(key)}
                    >
                      <X aria-hidden />
                    </WorkbenchIconAction>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
};
