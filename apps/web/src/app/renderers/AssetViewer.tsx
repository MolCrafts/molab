import { Archive, Download } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { assetsApi } from "@/api";
import type { AssetVersionResponse } from "@/api/generated/models/AssetVersionResponse";
import { DashboardCanvas, EntityPage, OverviewSurface } from "@/app/components/entity";
import type { ApiAssetResponse, ScopedRendererProps } from "@/app/types";
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
  const projectId = summary?.projectId ?? null;
  const [asset, setAsset] = useState<ApiAssetResponse | null>(null);
  const [versions, setVersions] = useState<AssetVersionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // One loader, called by the mount effect and by Retry alike — so a retry
  // repeats exactly what failed rather than a second copy of it.
  const load = useCallback(
    (signal: { cancelled: boolean }) => {
      setAsset(null);
      setVersions([]);
      setError(null);
      if (!projectId) return;
      setLoading(true);
      Promise.all([
        assetsApi.getProjectAsset(projectId, selection.objectId),
        assetsApi.listVersions(projectId, selection.objectId),
      ])
        .then(([nextAsset, nextVersions]) => {
          if (signal.cancelled) return;
          setAsset(nextAsset);
          setVersions(nextVersions);
        })
        .catch((reason: unknown) => {
          if (signal.cancelled) return;
          setError(reason instanceof Error ? reason.message : "Failed to load asset");
        })
        .finally(() => {
          if (!signal.cancelled) setLoading(false);
        });
    },
    [projectId, selection.objectId],
  );

  useEffect(() => {
    const signal = { cancelled: false };
    load(signal);
    return () => {
      signal.cancelled = true;
    };
  }, [load]);

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
        action={<WorkbenchRetryAction onClick={() => load({ cancelled: false })} />}
      />
    );
  }
  if (loading && !asset) {
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
            <Download className="h-3.5 w-3.5" />
          </a>
        </WorkbenchIconAction>
      }
      tabs={[
        {
          value: "overview",
          label: "Overview",
          content: (
            <OverviewSurface>
              <DashboardCanvas className="max-w-4xl space-y-8">
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
                  content version promoted from an Artifact.
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
              <DashboardCanvas className="max-w-5xl">
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
                        <TableHead>Source artifact</TableHead>
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
                            {version.sourceArtifactId}
                          </TableCell>
                          <TableCell className="font-mono text-micro">{version.digest}</TableCell>
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
