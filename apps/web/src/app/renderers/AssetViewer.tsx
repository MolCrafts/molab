import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import {
  Archive,
  Clock,
  Download,
  Import,
  Minus,
  Package,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import { assetsApi, assetVersionOrigin } from "@/api";
import {
  BYTES_EXPR,
  type CountBar,
  CountBars,
  DashboardCanvas,
  EmptyState,
  EntityPage,
  GaugeSection,
  Instrument,
  InstrumentStrip,
  OverviewCanvas,
  OverviewList,
  OverviewSurface,
  Tally,
} from "@/app/components/entity";
import { assetDetailQueryOptions, assetVersionsQueryOptions } from "@/app/state/entityQueries";
import type { ScopedRendererProps } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { formatBytes } from "@/lib/format-bytes";
import { formatRelative } from "@/lib/format-time";

export const AssetViewer = ({
  selection,
  snapshot,
}: ScopedRendererProps<"assets">): JSX.Element => {
  const [tab, setTab] = useState("overview");
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
  const ordered = [...versions].sort((left, right) => left.version - right.version);
  const latest = ordered[ordered.length - 1] ?? null;
  const previous = ordered[ordered.length - 2] ?? null;
  const sizeChange =
    latest &&
    previous &&
    typeof latest.size === "number" &&
    typeof previous.size === "number" &&
    previous.size > 0
      ? Math.round(((latest.size - previous.size) / previous.size) * 100)
      : null;
  const promoted = ordered.filter((version) => version.originKind === "artifact").length;
  const imported = ordered.filter((version) => version.originKind === "import").length;
  const sizeBars: CountBar[] = ordered.flatMap((version) =>
    typeof version.size === "number" && version.size >= 0
      ? [
          {
            key: version.id,
            label: `v${version.version}`,
            value: version.size,
            readout: formatBytes(version.size),
            // One fact per line: a narrow chart cannot hold a long origin on one row.
            tip: [
              `v${version.version} · ${formatBytes(version.size)}`,
              assetVersionOrigin(version),
              formatDateTime(version.createdAt),
            ].join("\n"),
          },
        ]
      : [],
  );
  const openVersions = (): void => setTab("versions");
  const versionsTable =
    versions.length === 0 ? (
      <WorkbenchOperationState
        kind={asset ? "empty" : "loading"}
        title={asset ? "No versions" : "Loading versions"}
        detail={asset ? "Promote an Artifact to create this asset's first version." : undefined}
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
              <TableCell className="font-mono text-label">{assetVersionOrigin(version)}</TableCell>
              <TableCell className="font-mono text-micro">{version.digest ?? ""}</TableCell>
              <TableCell className="font-mono text-label">{formatBytes(version.size)}</TableCell>
              <TableCell className="text-label">{formatDateTime(version.createdAt)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
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
          content:
            ordered.length === 0 ? (
              <OverviewCanvas>
                <EmptyState
                  title="No versions yet"
                  description="Promote an Artifact to create this asset's first version."
                />
              </OverviewCanvas>
            ) : (
              <OverviewCanvas>
                <InstrumentStrip label="Asset gauges" lead={false}>
                  <Instrument
                    title="Versions"
                    figure={ordered.length}
                    caption={
                      latest ? (
                        <Tally
                          icon={Clock}
                          value={`v${latest.version} · ${formatRelative(latest.createdAt)}`}
                          label={`Latest v${latest.version}, ${formatRelative(latest.createdAt)}`}
                        />
                      ) : undefined
                    }
                    onSelect={openVersions}
                    selectHint="Versions"
                    selectLabel={`${ordered.length} versions. Open the list`}
                  />
                  <Instrument
                    title="Size"
                    figure={latest ? formatBytes(latest.size) : "—"}
                    caption={
                      sizeChange === null ? undefined : (
                        <Tally
                          icon={sizeChange > 0 ? TrendingUp : sizeChange < 0 ? TrendingDown : Minus}
                          value={`${sizeChange > 0 ? "+" : ""}${sizeChange}%`}
                          label={`${sizeChange > 0 ? "+" : ""}${sizeChange}% vs v${previous?.version}`}
                        />
                      )
                    }
                  />
                  <Instrument
                    title="Origin"
                    caption={
                      <span className="flex items-center gap-6 text-title text-foreground">
                        <Tally
                          icon={Package}
                          value={promoted}
                          label={`${promoted} promoted from runs`}
                        />
                        <Tally icon={Import} value={imported} label={`${imported} imported`} />
                      </span>
                    }
                  />
                </InstrumentStrip>
                <GaugeSection title="Size by version">
                  {sizeBars.length > 0 ? (
                    <CountBars
                      bars={sizeBars}
                      label="Size of each asset version"
                      orientation="vertical"
                      valueExpr={BYTES_EXPR}
                      onPick={openVersions}
                    />
                  ) : (
                    <p className="text-label text-muted-foreground">No version records a size.</p>
                  )}
                </GaugeSection>
              </OverviewCanvas>
            ),
        },
        {
          value: "versions",
          label: `Versions (${versions.length})`,
          content: (
            <OverviewSurface>
              <DashboardCanvas>
                <OverviewList title="Versions">{versionsTable}</OverviewList>
              </DashboardCanvas>
            </OverviewSurface>
          ),
        },
      ]}
      activeTab={tab}
      onActiveTabChange={setTab}
    />
  );
};
