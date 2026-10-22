import { type JSX, useMemo } from "react";
import { EmptyState, EntityTabBar, EntityTabContent, EntityTabs } from "@/app/components/entity";
import type { RendererProps } from "@/app/types";
import type { DiscoveredFile } from "@/plugins/types";
import { MolplotObservablesTab } from "./MolplotObservablesTab";
import { RunMetricsTab } from "./RunMetricsTab";

type Props = RendererProps & { discoveredFiles: DiscoveredFile[] };

/** One host-owned MolPlot surface for scalar streams and declared plot artifacts. */
export const MolplotRunTab = (props: Props): JSX.Element => {
  const scalarFiles = useMemo(
    () => props.discoveredFiles.filter((file) => file.name.toLowerCase().endsWith(".mlp.jsonl")),
    [props.discoveredFiles],
  );
  const plotFiles = useMemo(
    () => props.discoveredFiles.filter((file) => file.name.toLowerCase().endsWith(".mlp.vl.json")),
    [props.discoveredFiles],
  );
  if (!props.executionId) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState
          title="Select an execution"
          description="MolPlot visualizes outputs from one physical execution."
        />
      </div>
    );
  }
  if (scalarFiles.length === 0)
    return <MolplotObservablesTab {...props} discoveredFiles={plotFiles} />;
  if (plotFiles.length === 0) return <RunMetricsTab {...props} discoveredFiles={scalarFiles} />;
  return (
    <EntityTabs defaultValue="scalars" className="h-full min-h-0">
      <EntityTabBar
        tabs={[
          { value: "scalars", label: "Scalars" },
          { value: "plots", label: "Plots" },
        ]}
      />
      <EntityTabContent value="scalars" className="m-0 min-h-0 flex-1">
        <RunMetricsTab {...props} discoveredFiles={scalarFiles} />
      </EntityTabContent>
      <EntityTabContent value="plots" className="m-0 min-h-0 flex-1">
        <MolplotObservablesTab {...props} discoveredFiles={plotFiles} />
      </EntityTabContent>
    </EntityTabs>
  );
};
