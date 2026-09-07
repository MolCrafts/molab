import { type JSX, useMemo } from "react";
import { EmptyState } from "@/app/components/entity";
import type { RendererProps } from "@/app/types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
    <Tabs defaultValue="scalars" className="flex h-full min-h-0 flex-col">
      <div className="flex h-[35px] items-center border-b border-border bg-surface-subtle px-3">
        <TabsList variant="line" className="h-full gap-4 rounded-none bg-transparent p-0">
          <TabsTrigger value="scalars" className="h-full rounded-none px-0">
            Scalars
          </TabsTrigger>
          <TabsTrigger value="plots" className="h-full rounded-none px-0">
            Plots
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="scalars" className="m-0 min-h-0 flex-1">
        <RunMetricsTab {...props} discoveredFiles={scalarFiles} />
      </TabsContent>
      <TabsContent value="plots" className="m-0 min-h-0 flex-1">
        <MolplotObservablesTab {...props} discoveredFiles={plotFiles} />
      </TabsContent>
    </Tabs>
  );
};
