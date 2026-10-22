import { useWorkspaceTabVisible } from "@/app/dashboard/useWorkspaceTab";
import type { LeftPanelView, WorkspaceSnapshot } from "@/app/types";
import { LeftIconRail } from "@/components/layout/ExplorerShell";
import { useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { prefetchNavigationView } from "./prefetch";
import { managementNavigationContribution, railNavigationContributions } from "./sections";

export interface NavigationRailProps {
  activeId: LeftPanelView;
  /** Served directory kind. Levels above it drop off the rail. */
  scopeKind?: string | null;
  snapshot: WorkspaceSnapshot;
  onSelect: (id: LeftPanelView) => void;
}

/** Molab adapter from product section metadata to the shared icon rail. */
export const NavigationRail = ({
  activeId,
  scopeKind,
  snapshot,
  onSelect,
}: NavigationRailProps): JSX.Element => {
  useWorkbenchGeneration();
  const workspaceTab = useWorkspaceTabVisible(snapshot);
  const items = railNavigationContributions(scopeKind).filter(
    (item) => item.id !== "dashboard" || workspaceTab,
  );
  const footer = managementNavigationContribution() ?? null;
  return (
    <LeftIconRail
      items={items.map((contribution, index, all) => ({
        ...contribution,
        separatorBefore:
          contribution.placement === "secondary" && all[index - 1]?.placement !== "secondary",
        onIntent: () => prefetchNavigationView(contribution.id),
      }))}
      activeId={activeId}
      onSelect={(id) => onSelect(id as LeftPanelView)}
      footer={footer ? { ...footer, onIntent: () => prefetchNavigationView(footer.id) } : null}
    />
  );
};
