import { useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Blocks,
  Copy,
  ExternalLink,
  FlaskConical,
  FolderTree,
  PlayCircle,
  RefreshCw,
} from "lucide-react";
import type { ReactNode } from "react";
import { EMPTY_COPY, StatusBadge } from "@/app/components/entity";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { type TreeNode, TreeView } from "@/app/panels/TreeView";
import { prefetchRenderer } from "@/app/renderers/lazyRenderers";
import { assetDetailQueryOptions, assetVersionsQueryOptions } from "@/app/state/entityQueries";
import type { AssetSummary } from "@/app/types";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";

const copyText = async (text: string): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    console.warn("Failed to copy asset ID:", error);
  }
};

const CompactCount = ({ children }: { children: ReactNode }): JSX.Element => (
  <span className="font-mono text-micro text-muted-foreground">{children}</span>
);

const filterAssets = (items: AssetSummary[], searchQuery: string): AssetSummary[] => {
  if (!searchQuery) return items;
  const lower = searchQuery.toLowerCase();
  return items.filter(
    (item) =>
      item.name.toLowerCase().includes(lower) || item.summary?.toLowerCase().includes(lower),
  );
};

export const buildAssetExplorerNodes = ({
  snapshot,
  searchQuery,
  onSelect,
  onPrefetchAsset,
}: Pick<NavigationExplorerProps, "snapshot" | "searchQuery" | "onSelect"> & {
  onPrefetchAsset?: (asset: AssetSummary) => void;
}): TreeNode[] => {
  // Catalog and scoped loads can overlap; one asset must still produce one row.
  const byId = new Map<string, AssetSummary>();
  for (const asset of filterAssets(snapshot.assets, searchQuery)) {
    if (!byId.has(asset.id)) byId.set(asset.id, asset);
  }
  const assets = [...byId.values()];

  const projectName = (id: string): string =>
    snapshot.projects.find((project) => project.id === id)?.name ?? id;
  const experimentName = (id: string): string =>
    snapshot.experiments.find((experiment) => experiment.id === id)?.name ?? id;
  const runName = (id: string): string => snapshot.runs.find((run) => run.id === id)?.name ?? id;

  const assetLeaf = (asset: AssetSummary): TreeNode => ({
    id: asset.id,
    label: asset.name,
    icon: Archive,
    iconClassName: "text-muted-foreground",
    right: <StatusBadge status={asset.status} size="sm" />,
    onPrefetch: () => onPrefetchAsset?.(asset),
    onSelect: () => onSelect({ objectType: "asset", objectId: asset.id }),
    actions: [
      {
        id: "open",
        label: "Open asset",
        icon: ExternalLink,
        onSelect: () => onSelect({ objectType: "asset", objectId: asset.id }),
      },
      {
        id: "copy-id",
        label: "Copy asset ID",
        icon: Copy,
        onSelect: () => void copyText(asset.id),
      },
    ],
  });

  const groupBy = <T,>(rows: AssetSummary[], key: (asset: AssetSummary) => T | undefined) => {
    const direct: AssetSummary[] = [];
    const groups = new Map<T, AssetSummary[]>();
    for (const asset of rows) {
      const value = key(asset);
      if (value === undefined) direct.push(asset);
      else groups.set(value, [...(groups.get(value) ?? []), asset]);
    }
    return { direct, groups };
  };
  const byLabel = (left: TreeNode, right: TreeNode): number =>
    left.label.localeCompare(right.label);
  const { direct: workspaceAssets, groups: byProject } = groupBy(
    assets,
    (asset) => asset.projectId,
  );

  const projectNodes = [...byProject.entries()]
    .map(([projectId, projectAssets]): TreeNode => {
      const { direct: projectDirect, groups: byExperiment } = groupBy(
        projectAssets,
        (asset) => asset.experimentId,
      );
      const experimentNodes = [...byExperiment.entries()]
        .map(([experimentId, experimentAssets]): TreeNode => {
          const { direct: experimentDirect, groups: byRun } = groupBy(
            experimentAssets,
            (asset) => asset.runId,
          );
          const runNodes = [...byRun.entries()]
            .map(
              ([runId, runAssets]): TreeNode => ({
                id: `asset-run-${runId}`,
                label: runName(runId),
                icon: PlayCircle,
                iconClassName: "text-muted-foreground",
                right: <CompactCount>{runAssets.length}</CompactCount>,
                onSelect: () => onSelect({ objectType: "run", objectId: runId }),
                children: [...runAssets]
                  .sort((left, right) => left.name.localeCompare(right.name))
                  .map(assetLeaf),
              }),
            )
            .sort(byLabel);
          return {
            id: `asset-exp-${experimentId}`,
            label: experimentName(experimentId),
            icon: FlaskConical,
            iconClassName: "text-muted-foreground",
            right: <CompactCount>{experimentAssets.length}</CompactCount>,
            onSelect: () => onSelect({ objectType: "experiment", objectId: experimentId }),
            children: [...experimentDirect.map(assetLeaf), ...runNodes],
          };
        })
        .sort(byLabel);
      return {
        id: `asset-proj-${projectId}`,
        label: projectName(projectId),
        icon: Blocks,
        iconClassName: "text-muted-foreground",
        right: <CompactCount>{projectAssets.length}</CompactCount>,
        onSelect: () => onSelect({ objectType: "project", objectId: projectId }),
        children: [...projectDirect.map(assetLeaf), ...experimentNodes],
      };
    })
    .sort(byLabel);

  if (workspaceAssets.length > 0) {
    projectNodes.push({
      id: "asset-workspace",
      label: "Workspace",
      icon: FolderTree,
      iconClassName: "text-muted-foreground",
      right: <CompactCount>{workspaceAssets.length}</CompactCount>,
      children: workspaceAssets.map(assetLeaf),
    });
  }
  return projectNodes;
};

/** Complete feature-owned explorer surface for the cross-project asset inventory. */
export const AssetsExplorer = (
  props: Pick<
    NavigationExplorerProps,
    "snapshot" | "selection" | "searchQuery" | "onSelect" | "onRefresh"
  >,
): JSX.Element => {
  const queryClient = useQueryClient();
  const nodes = buildAssetExplorerNodes({
    ...props,
    onPrefetchAsset: (asset) => {
      prefetchRenderer("asset");
      if (!asset.projectId) return;
      void queryClient.prefetchQuery(assetDetailQueryOptions(asset.projectId, asset.id));
      void queryClient.prefetchQuery(assetVersionsQueryOptions(asset.projectId, asset.id));
    },
  });
  const actions = (
    <WorkbenchIconAction label="Refresh assets" kind="ghost" onClick={props.onRefresh}>
      <RefreshCw className="size-4" />
    </WorkbenchIconAction>
  );

  return (
    <LeftExplorer title="Assets" actions={actions}>
      <TreeView
        nodes={nodes}
        activeId={props.selection?.objectId}
        emptyTitle={EMPTY_COPY.assets.title}
      />
    </LeftExplorer>
  );
};
