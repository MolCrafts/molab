import { SelectionPanel } from "@/app/compare";
import { NavigationExplorerHost } from "@/app/navigation/NavigationExplorerHost";
import { getNavigationContribution } from "@/app/navigation/sections";
import type { LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { ExplorerDock } from "@/components/layout/ExplorerShell";
import { useWorkbenchGeneration } from "@/plugins/contributions/workbench";

const DOCK = { id: "molab-pinned-dock", autoSaveId: "molab.shell.v3.pinned" } as const;

interface LeftPanelProps {
  view: LeftPanelView;
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  searchQuery?: string;
  /** Pinned (the compare selection) is collapsed by default (L00). */
  pinnedExpanded: boolean;
  onTogglePinned: () => void;
  onSelect: (selection: Selection) => void;
  onOpenWorkspace: (path: string, options?: { createIfMissing?: boolean }) => Promise<void>;
  onCreateDirectory: (path: string) => void;
  onCreateFile: (path: string) => void;
  onRefresh: () => void;
  onExpandDirectory?: (dirPath: string) => void;
  onExpandProject?: (projectId: string) => void;
  onExpandExperiment?: (projectId: string, experimentId: string) => void;
  isProjectExpanded?: (projectId: string) => boolean;
  isExperimentExpanded?: (projectId: string, experimentId: string) => boolean;
  dataEpoch?: number;
}

/**
 * The side bar (L00): the active section's explorer over the **Pinned**
 * section. The activity bar is the shell's, outside this column. Each feature
 * owns its explorer, queries, and dialogs.
 */
export const LeftPanel = (props: LeftPanelProps): JSX.Element => {
  const { view, snapshot, pinnedExpanded, onTogglePinned, dataEpoch = 0 } = props;
  useWorkbenchGeneration();
  const contribution = getNavigationContribution(view);
  const explorerHost = (
    <NavigationExplorerHost
      contribution={contribution}
      explorerProps={{
        snapshot,
        selection: props.selection,
        searchQuery: props.searchQuery ?? "",
        onSelect: props.onSelect,
        onRefresh: props.onRefresh,
        fileSystem: {
          onOpenWorkspace: props.onOpenWorkspace,
          onCreateDirectory: props.onCreateDirectory,
          onCreateFile: props.onCreateFile,
          onExpandDirectory: props.onExpandDirectory,
          dataEpoch,
        },
        projectTree: {
          onExpandProject: props.onExpandProject,
          onExpandExperiment: props.onExpandExperiment,
          isProjectExpanded: props.isProjectExpanded,
          isExperimentExpanded: props.isExperimentExpanded,
          dataEpoch,
        },
      }}
    />
  );

  // The comparison belongs to the side bar, not to one explorer: runs are
  // gathered from Projects and Files as readily as from the Runs table.
  const pinned = (
    <SelectionPanel snapshot={snapshot} expanded={pinnedExpanded} onToggle={onTogglePinned} />
  );

  return (
    <aside
      aria-label="Side bar"
      className="flex h-full min-h-0 flex-col bg-surface-subtle"
      data-shell-region="sidebar"
    >
      {contribution.shellMode !== "explorer" ? (
        explorerHost
      ) : (
        // One structure either way: folding Pinned must not remount the tree.
        <ExplorerDock {...DOCK} dock={pinned} collapsed={!pinnedExpanded}>
          {explorerHost}
        </ExplorerDock>
      )}
    </aside>
  );
};
