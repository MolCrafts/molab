import { RefreshCw } from "lucide-react";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";

/** Compatibility copy for legacy /activity routes; no primary rail contribution. */
export const ActivityExplorer = ({
  onRefresh,
}: Pick<NavigationExplorerProps, "onRefresh">): JSX.Element => (
  <LeftExplorer
    title="Activity"
    actions={
      <WorkbenchIconAction label="Refresh activity" kind="ghost" onClick={onRefresh}>
        <RefreshCw className="size-4" />
      </WorkbenchIconAction>
    }
  >
    <div className="space-y-2 text-label text-muted-foreground">
      <p className="font-medium text-foreground">Event spine</p>
      <p>
        The center panel shows the workspace-wide activity timeline. Filter by event type there.
      </p>
    </div>
  </LeftExplorer>
);
