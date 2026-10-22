import { RefreshCw } from "lucide-react";
import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";
import { computeFacetCounts } from "./aggregates";
import { parseFilterParams, writeFilterParams } from "./filterParams";
import { RunsFacetPanel } from "./RunsFacetPanel";
import type { WorkspaceRunsFilters } from "./types";
import { useWorkspaceRuns } from "./useWorkspaceRuns";

/** Feature-owned explorer contribution for the global Runs inventory. */
export const RunsExplorer = ({
  onRefresh,
}: Pick<NavigationExplorerProps, "onRefresh">): JSX.Element => {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo<WorkspaceRunsFilters>(
    () => parseFilterParams(searchParams),
    [searchParams],
  );
  const { rows } = useWorkspaceRuns();
  const facets = useMemo(() => computeFacetCounts(rows, filters), [rows, filters]);

  const actions = (
    <WorkbenchIconAction label="Refresh runs" kind="ghost" onClick={onRefresh}>
      <RefreshCw className="size-4" />
    </WorkbenchIconAction>
  );

  return (
    <LeftExplorer title="Runs" actions={actions}>
      <RunsFacetPanel
        facets={facets}
        filters={filters}
        onFiltersChange={(next) => {
          setSearchParams((previous) => writeFilterParams(previous, next), { replace: true });
        }}
      />
    </LeftExplorer>
  );
};
