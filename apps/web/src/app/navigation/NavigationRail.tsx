import type { LeftPanelView } from "@/app/types";
import { LeftIconRail } from "@/components/layout/ExplorerShell";
import { useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { prefetchNavigationView } from "./prefetch";
import { managementNavigationContribution, railNavigationContributions } from "./sections";

export interface NavigationRailProps {
  activeId: LeftPanelView;
  onSelect: (id: LeftPanelView) => void;
}

/** Molab adapter from product section metadata to the shared icon rail. */
export const NavigationRail = ({ activeId, onSelect }: NavigationRailProps): JSX.Element => {
  useWorkbenchGeneration();
  const items = railNavigationContributions();
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
