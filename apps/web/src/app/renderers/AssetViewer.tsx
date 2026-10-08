import { useQuery } from "@tanstack/react-query";
import { Archive, Download } from "lucide-react";
import { assetsApi, assetVersionOrigin } from "@/api";
import { DashboardCanvas, EntityPage, OverviewSurface } from "@/app/components/entity";
import { assetDetailQueryOptions, assetVersionsQueryOptions } from "@/app/state/entityQueries";
import type { ScopedRendererProps } from "@/app/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { formatBytes } from "@/lib/format-bytes";

export const AssetViewer = ({
  selection,
  snapshot,
}: ScopedRendererProps<"assets">): JSX.Element => {
  const summary = snapshot.assets.find((item) => item.id === selection.objectId) ?? null;
  const projectId = summary?.projectId ?? "";
  const assetQuery = useQuery({
    ...assetDetailQueryOptions(projectId, selection.objectId),
    enabled: Boolean(summary?.projectId),
  });
  const versionsQuery = useQuery({
    ...assetVersionsQueryOptions(projectId, selection.objectId),
    enabled: Boolean(summary?.projectId),
  });
  const asset = assetQuery.data ?? null;
  const versions = versionsQuery.data ?? [];
  const error =
    assetQuery.error instanceof Error
      ? assetQuery.error.message
      : versionsQuery.error instanceof Error
        ? versionsQuery.error.message
        : assetQuery.error || versionsQuery.error
          ? "Failed to load asset"
          : null;
  const retry = (): void => {
    void assetQuery.refetch();
    void versionsQuery.refetch();
  };

  if (!summary || !projectId) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="Asset not found"
        detail="Assets are addressed inside a Project data space."
      />
    );
  }
  if (error) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Cannot load asset"
        detail={error}
        action={<WorkbenchRetryAction onClick={retry} />}
      />
    );
  }
  if ((assetQuery.isPending || versionsQuery.isPending) && !asset) {
    return <WorkbenchOperationState kind="loading" title="Loading asset" />;
  }

  const title = asset?.title ?? summary.name;
  return (
    <EntityPage
      icon={Archive}
      title={title}
      actions={
        <WorkbenchIconAction label="Download latest asset version" asChild>
          <a href={assetsApi.downloadUrl(projectId, selection.objectId)} download>
            <Download className="size-3.5" />
          </a>
        </WorkbenchIconAction>
      }
      tabs={[
        {
          value: "overview",
          label: "Overview",
          content: (
            <OverviewSurface>
              <DashboardCanvas>
                <dl className="grid gap-3 text-label sm:grid-cols-[10rem_1fr]">
                  <dt className="text-muted-foreground">Asset ID</dt>
                  <dd className="break-all font-mono">{selection.objectId}</dd>
                  <dt className="text-muted-foreground">Project</dt>
                  <dd className="break-all font-mono">{projectId}</dd>
                  <dt className="text-muted-foreground">Created</dt>
                  <dd>{asset ? formatDateTime(asset.createdAt) : "Loading…"}</dd>
                  <dt className="text-muted-foreground">Versions</dt>
                  <dd className="font-mono">{versions.length}</dd>
                </dl>
                <p className="text-label text-muted-foreground">
                  Asset identity is stable across storage locations. Each row below is an immutable
                  content version promoted from an Artifact or imported.
                </p>
              </DashboardCanvas>
            </OverviewSurface>
          ),
        },
        {
          value: "versions",
          label: `Versions (${versions.length})`,
          content: (
            <OverviewSurface>
              <DashboardCanvas>
                {versions.length === 0 ? (
                  <WorkbenchOperationState
                    kind={asset ? "empty" : "loading"}
                    title={asset ? "No versions" : "Loading versions"}
                    detail={
                      asset
                        ? "Promote an Artifact to create this asset's first version."
                        : undefined
                    }
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Version</TableHead>
                        <TableHead>Origin</TableHead>
                        <TableHead>Content</TableHead>
                        <TableHead>Size</TableHead>
                        <TableHead>Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {versions.map((version) => (
                        <TableRow key={version.id}>
                          <TableCell className="font-mono">v{version.version}</TableCell>
                          <TableCell className="font-mono text-label">
                            {assetVersionOrigin(version)}
                          </TableCell>
                          <TableCell className="font-mono text-micro">
                            {version.digest ?? "—"}
                          </TableCell>
                          <TableCell className="font-mono text-label">
                            {formatBytes(version.size)}
                          </TableCell>
                          <TableCell className="text-label">
                            {formatDateTime(version.createdAt)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </DashboardCanvas>
            </OverviewSurface>
          ),
        },
      ]}
      defaultTab="overview"
    />
  );
};
