import { ServerCog } from "lucide-react";
import { useMemo } from "react";
import { MetadataInspector } from "@/app/renderers/MetadataInspector";
import type { RendererProps } from "@/app/types";
import { WorkbenchTag } from "@/components/workbench";

const formatExecutorLabel = (key: string): string => {
  return key.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
};

export const MolqRunInspector = (props: RendererProps): JSX.Element => {
  const run = useMemo(() => {
    return props.snapshot.runs.find((item) => item.id === props.selection.objectId) ?? null;
  }, [props.selection.objectId, props.snapshot.runs]);

  const execution = run?.executionHistory.find((item) => item.executionId === props.executionId);
  if (execution?.executor.backend !== "molq") {
    return <MetadataInspector {...props} />;
  }

  const rows = Object.entries(execution.executor);

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-[35px] items-center justify-between border-b border-border bg-surface-subtle px-3">
        <div className="flex min-w-0 items-center gap-2">
          <ServerCog className="h-3.5 w-3.5 text-muted-foreground" />
          <h2 className="truncate text-micro font-medium uppercase tracking-wide text-muted-foreground">
            Executor
          </h2>
        </div>
        <WorkbenchTag className="h-5 px-2 text-micro uppercase tracking-wide">molq</WorkbenchTag>
      </div>
      <dl className="flex-1 divide-y divide-border/50 overflow-auto">
        {rows.map(([key, value]) => (
          <div key={key} className="px-3 py-2">
            <dt className="text-micro font-medium uppercase tracking-wide text-muted-foreground">
              {formatExecutorLabel(key)}
            </dt>
            <dd className="mt-1 break-words font-mono text-label text-foreground">
              {typeof value === "string" ? value : JSON.stringify(value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
};
