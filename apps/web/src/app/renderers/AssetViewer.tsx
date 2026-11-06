import { useQuery } from "@tanstack/react-query";
import { Archive, Download } from "lucide-react";
import { useState } from "react";
import { assetOriginText, assetsApi } from "@/api";
import { EntityPage, OverviewCanvas, OverviewList, OverviewSurface } from "@/app/components/entity";
import { assetDetailQueryOptions } from "@/app/state/entityQueries";
import type { ScopedRendererProps } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { formatBytes } from "@/lib/format-bytes";

const extraText = (extra: Record<string, unknown> | undefined, key: string): string | null => {
  const value = extra?.[key];
  return typeof value === "string" && value ? value : null;
};

const extraNumber = (extra: Record<string, unknown> | undefined, key: string): number | null => {
  const value = extra?.[key];
  return typeof value === "number" ? value : null;
};

export const AssetViewer = ({
  selection,
  snapshot,
}: ScopedRendererProps<"assets" | "runs">): JSX.Element => {
  const [tab, setTab] = useState("overview");
  const summary = snapshot.assets.find((item) => item.id === selection.objectId) ?? null;
  const projectId = summary?.projectId ?? "";
  const assetQuery = useQuery({
    ...assetDetailQueryOptions(projectId, selection.objectId),
    enabled: Boolean(summary?.projectId),
  });
  const asset = assetQuery.data ?? null;
  const error =
    assetQuery.error instanceof Error
      ? assetQuery.error.message
      : assetQuery.error
        ? "Failed to load asset"
        : null;

  if (!summary) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="Asset not found"
        detail="This asset is not in the loaded catalog."
      />
    );
  }
  if (!projectId) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="No project for this asset"
        detail="Assets are addressed inside a Project."
      />
    );
  }
  if (error) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Cannot load asset"
        detail={error}
        action={<WorkbenchRetryAction onClick={() => void assetQuery.refetch()} />}
      />
    );
  }
  if (assetQuery.isPending && !asset) {
    return <WorkbenchOperationState kind="loading" title="Loading asset" />;
  }

  const extra = asset?.extra;
  const title = asset?.title ?? summary.name;
  const origin = assetOriginText({
    originKind: extraText(extra, "originKind"),
    runId: extraText(extra, "runId"),
    executionId: extraText(extra, "executionId"),
    task: extraText(extra, "task"),
    uri: extraText(extra, "uri"),
  });
  const digest = extraText(extra, "digest") ?? "—";
  const size = extraNumber(extra, "size");
  const mediaType = extraText(extra, "mediaType") ?? asset?.kind ?? "—";
  const ref = asset?.ref ?? summary.ref ?? "—";
  const consumers = snapshot.runs.filter((run) => (run.inputs ?? []).includes(selection.objectId));
  const rows: Array<[string, string]> = [
    ["Ref", ref],
    ["Content", digest],
    ["Size", size == null ? "—" : formatBytes(size)],
    ["Media type", mediaType],
    ["File", asset?.path || "—"],
    ["Origin", origin],
    ["Registered", asset ? formatDateTime(asset.createdAt) : "—"],
  ];

  return (
    <EntityPage
      icon={Archive}
      title={title}
      actions={
        <WorkbenchIconAction label="Download asset" asChild>
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
            <OverviewCanvas>
              <OverviewSurface>
                <OverviewList title="This file">
                  <dl className="grid gap-2">
                    {rows.map(([label, value]) => (
                      <div key={label} className="grid grid-cols-[8rem_1fr] gap-3">
                        <dt className="text-label text-muted-foreground">{label}</dt>
                        <dd className="break-all font-mono text-label">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </OverviewList>
              </OverviewSurface>
            </OverviewCanvas>
          ),
        },
        {
          value: "runs",
          label: `Runs (${consumers.length})`,
          content: (
            <OverviewSurface>
              {consumers.length === 0 ? (
                <WorkbenchOperationState
                  kind="empty"
                  title="No loaded run names this asset"
                  detail="A run lists it in inputs when the next calculation should open it."
                />
              ) : (
                <OverviewList title="Runs that open this file">
                  <ul className="grid gap-2">
                    {consumers.map((run) => (
                      <li key={run.id} className="font-mono text-label">
                        {run.name || run.id}
                      </li>
                    ))}
                  </ul>
                </OverviewList>
              )}
            </OverviewSurface>
          ),
        },
      ]}
      activeTab={tab}
      onActiveTabChange={setTab}
    />
  );
};
