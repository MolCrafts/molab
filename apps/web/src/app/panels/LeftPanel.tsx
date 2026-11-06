import { SelectionPanel } from "@/app/compare";
import { NavigationExplorerHost } from "@/app/navigation/NavigationExplorerHost";
import { NavigationRail } from "@/app/navigation/NavigationRail";
import { getNavigationContribution } from "@/app/navigation/sections";
import type { LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";
import { ExplorerDock } from "@/components/layout/ExplorerShell";
import { useWorkbenchGeneration } from "@/plugins/contributions/workbench";

const DOCK = { id: "molab-explorer-dock", autoSaveId: "molab.explorerDock.v2" } as const;

interface LeftPanelProps {
  view: LeftPanelView;
  selection: Selection | null;
  snapshot: WorkspaceSnapshot;
  searchQuery?: string;
  onViewChange: (view: LeftPanelView) => void;
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

/** Navigation adapter. Each feature owns its explorer, queries, and dialogs. */
export const LeftPanel = ({
  view,
  selection,
  snapshot,
  onViewChange,
  onSelect,
  onOpenWorkspace,
  onCreateDirectory,
  onCreateFile,
  onRefresh,
  onExpandDirectory,
  onExpandProject,
  onExpandExperiment,
  isProjectExpanded,
  isExperimentExpanded,
  dataEpoch = 0,
  searchQuery = "",
}: LeftPanelProps): JSX.Element => {
  useWorkbenchGeneration();
  const contribution = getNavigationContribution(view);
  const explorerHost = (
    <NavigationExplorerHost
      contribution={contribution}
      explorerProps={{
        snapshot,
        selection,
        searchQuery,
        onSelect,
        onRefresh,
        fileSystem: {
          onOpenWorkspace,
          onCreateDirectory,
          onCreateFile,
          onExpandDirectory,
          dataEpoch,
        },
        projectTree: {
          onExpandProject,
          onExpandExperiment,
          isProjectExpanded,
          isExperimentExpanded,
          dataEpoch,
        },
      }}
    />
  );

  return (
    <div className="flex h-full min-h-0">
      <NavigationRail
        activeId={view}
        scopeKind={snapshot.serveScope?.kind}
        snapshot={snapshot}
        onSelect={onViewChange}
      />
      {/* The comparison belongs to the panel, not to one explorer: runs are gathered
          from Projects and Files as readily as from the Runs table, and a staging
          area that disappears with its section cannot span two projects. */}
      {contribution.shellMode === "explorer" ? (
        <ExplorerDock {...DOCK} dock={<SelectionPanel snapshot={snapshot} />}>
          {explorerHost}
        </ExplorerDock>
      ) : (
        explorerHost
      )}
    </div>
  );
};
