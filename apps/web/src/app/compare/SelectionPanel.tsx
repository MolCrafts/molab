/**
 * The selection being assembled, docked at the foot of the left panel.
 *
 * Rows are the bag, grouped by category (an empty category is Ungrouped).
 * Move up / Move down reorder that bag. The hydrated project tree supplies
 * display names when the snapshot knows the entity.
 */

import { ArrowUpRight, ListX, X } from "lucide-react";
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

export const SelectionPanel = ({
  snapshot,
}: {
  snapshot: WorkspaceSnapshot;
}): JSX.Element | null => {
  const { entries, remove, clear } = useCompareSet();
  const visible = compareEntriesForWorkspaces(
    entries,
    snapshot.workspaces.map((workspace) => workspace.key),
  );
  const tree = useMemo(() => hydrateComparisonTree(visible, snapshot), [visible, snapshot]);

  if (visible.length === 0) return null;

  return (
    <section
      className="overflow-hidden border-t border-border px-2 py-2"
      aria-label="Compare selection"
    >
      <div className="flex items-center gap-2">
        <Link
          to="/compare"
          className="inline-flex min-w-0 items-center gap-1 text-label text-foreground hover:underline"
        >
          Compare
          <span className="font-mono text-micro tabular-nums text-muted-foreground">
            {visible.length}
          </span>
          <ArrowUpRight className="size-3.5 shrink-0" aria-hidden />
        </Link>
        <WorkbenchIconAction
          label="Clear selection"
          className="ml-auto text-muted-foreground"
          onClick={clear}
        >
          <ListX aria-hidden />
        </WorkbenchIconAction>
      </div>
      <ul className="mt-1 space-y-1">
        {visible.map((entry) => {
          const key = itemKey(entry.ref);
          const label = entryLabel(entry, tree);
          return (
            <li key={key} className="flex min-w-0 items-center gap-1">
              <span className="min-w-0 flex-1 truncate text-label" title={label}>
                {label}
                {entry.category ? (
                  <span className="ml-1 font-mono text-micro text-muted-foreground">
                    {entry.category}
                  </span>
                ) : null}
              </span>
              <WorkbenchIconAction
                label={`Remove ${label}`}
                kind="ghost"
                onClick={() => remove(key)}
              >
                <X className="size-3.5" />
              </WorkbenchIconAction>
            </li>
          );
        })}
      </ul>
    </section>
  );
};
