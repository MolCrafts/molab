import { NavigationExplorerHost } from "@/app/navigation/NavigationExplorerHost";
import { NavigationRail } from "@/app/navigation/NavigationRail";
import { getNavigationContribution } from "@/app/navigation/sections";
import type { LeftPanelView, Selection, WorkspaceSnapshot } from "@/app/types";

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

/**
 * Navigation adapter only. Product metadata lives in sections.tsx; each
 * feature contribution owns its explorer surface, queries, actions, and dialogs.
 */
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
}: LeftPanelProps): JSX.Element => (
  <div className="flex h-full min-h-0">
    <NavigationRail activeId={view} onSelect={onViewChange} />
    <NavigationExplorerHost
      contribution={getNavigationContribution(view)}
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
  </div>
);
