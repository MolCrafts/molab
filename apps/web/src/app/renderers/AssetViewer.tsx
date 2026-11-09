/**
 * An asset (L08): a sentence of where it sits, its lineage, and what is
 * inside it — nothing else on the page. A click on a lineage node opens that
 * node's details in a panel at the right (this asset's file facts and
 * citations, a run's attempt and parameters, an input, the import source).
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Skeleton,
} from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import { Archive, Download, Link2, MoreHorizontal } from "lucide-react";
import { type JSX, type ReactNode, useMemo, useState } from "react";
import { assetsApi } from "@/api";
import { AssetContent } from "@/app/assets/AssetContent";
import { AssetLineage, type LineageNodeSpec } from "@/app/assets/AssetLineage";
import {
  AssetDetails,
  copyText,
  DetailsPanel,
  ImportDetails,
  InputDetails,
  latestExecution,
  RunDetails,
} from "@/app/assets/AssetSections";
import { AssetKindIcon, AssetTile } from "@/app/assets/AssetTile";
import { assetContext, contextSentence, importSource } from "@/app/assets/assetContext";
import { kindOfAsset } from "@/app/assets/assetKinds";
import { EntityPage, StatusIcon } from "@/app/components/entity";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import { usePreview } from "@/app/preview/PreviewContext";
import { runLabel, withRunTitles } from "@/app/runs/runTitle";
import type { WorkspaceRunRow } from "@/app/runs/types";
import { assetDetailQueryOptions } from "@/app/state/entityQueries";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { AssetSummary, ScopedRendererProps } from "@/app/types";
import {
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { formatRelative } from "@/lib/format-time";
import { assetCitationsQueryOptions } from "@/plugins/knowledge/queries";

/** Which lineage node's details are open. */
type Picked =
  | { kind: "self" }
  | { kind: "origin" }
  | { kind: "input"; assetId: string }
  | { kind: "user"; key: string };

const runKey = (run: WorkspaceRunRow): string => `${run.projectId}/${run.id}`;

const extraText = (extra: Record<string, unknown> | undefined, key: string): string | null => {
  const value = extra?.[key];
  return typeof value === "string" && value ? value : null;
};

const samePick = (left: Picked | null, right: Picked): boolean =>
  left !== null && JSON.stringify(left) === JSON.stringify(right);

export const AssetViewer = (
  props: ScopedRendererProps<"assets" | "runs" | "experiments" | "workflows">,
): JSX.Element => {
  const { selection, snapshot } = props;
  const preview = usePreview();
  const { setSelection } = useNavigationState(snapshot);
  const [picked, setPicked] = useState<Picked | null>(null);
  const summary = snapshot.assets.find((item) => item.id === selection.objectId) ?? null;
  const projectId = summary?.projectId ?? "";
  const detail = useQuery({
    ...assetDetailQueryOptions(projectId, selection.objectId),
    enabled: Boolean(summary?.projectId),
  });
  const inventory = useScopeRuns({}, Boolean(summary));
  const citations = useQuery({
    ...assetCitationsQueryOptions(selection.objectId),
    enabled: Boolean(summary),
  });
  const runs = useMemo(() => withRunTitles(inventory.rows), [inventory.rows]);
  const context = useMemo(
    () => (summary ? assetContext(summary, snapshot.assets, runs) : null),
    [summary, snapshot.assets, runs],
  );

  if (!summary || !context) {
    return (
      <WorkbenchOperationState
        kind="empty"
        title="Asset not found"
        detail="This asset is not in the loaded catalog."
      />
    );
  }
  if (detail.error) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Cannot load asset"
        detail={detail.error instanceof Error ? detail.error.message : "Failed to load asset"}
        action={<WorkbenchRetryAction onClick={() => void detail.refetch()} />}
      />
    );
  }

  const asset = detail.data ?? null;
  const { producer, imported, kind } = context;
  const origin = summary.origin;
  const reference = asset?.ref ?? summary.ref ?? null;
  const file = asset?.path || null;
  const download = projectId ? assetsApi.downloadUrl(projectId, summary.id) : null;
  const toggle = (pick: Picked): void =>
    setPicked((current) => (samePick(current, pick) ? null : pick));
  const openRun = (run: WorkspaceRunRow): void =>
    preview.open({
      kind: "run",
      runId: run.id,
      projectId: run.projectId,
      experimentId: run.experimentId,
      workspaceKey: run.workspaceKey,
    });
  const openAsset = (item: AssetSummary): void =>
    setSelection({ objectType: "asset", objectId: item.id });

  const runNode = (run: WorkspaceRunRow, pick: Picked, sub?: string): LineageNodeSpec => ({
    key: runKey(run),
    label: runLabel(run),
    sub,
    status: latestExecution(run)?.status ?? null,
    mono: true,
    selected: samePick(picked, pick),
    onClick: () => toggle(pick),
  });
  const producerSub = [origin?.executionId, origin?.task ? `task ${origin.task}` : null]
    .filter(Boolean)
    .join(" · ");
  const originNode: LineageNodeSpec | null = imported
    ? {
        key: "import",
        label: importSource(origin?.uri ?? null),
        sub: `imported ${formatRelative(summary.updatedAt)}`,
        icon: <Link2 aria-hidden className="size-icon-sm flex-none text-muted-foreground" />,
        mono: true,
        selected: samePick(picked, { kind: "origin" }),
        onClick: () => toggle({ kind: "origin" }),
      }
    : producer
      ? runNode(producer, { kind: "origin" }, producerSub || undefined)
      : null;

  const panel = ((): ReactNode => {
    if (!picked) return null;
    const close = (): void => setPicked(null);
    if (picked.kind === "self")
      return (
        <DetailsPanel title={summary.name} icon={<AssetKindIcon kind={kind} />} onClose={close}>
          <AssetDetails
            asset={summary}
            reference={reference}
            digest={extraText(asset?.extra, "digest")}
            file={file}
            registered={asset?.createdAt ?? summary.updatedAt}
            citations={citations.data ?? []}
            citationsLoading={citations.isPending}
            onOpenCitation={(path) => setSelection({ objectType: "knowledge", objectId: path })}
          />
        </DetailsPanel>
      );
    if (picked.kind === "origin" && imported)
      return (
        <DetailsPanel
          title={importSource(origin?.uri ?? null)}
          icon={<Link2 aria-hidden className="size-icon-sm text-muted-foreground" />}
          onClose={close}
        >
          <ImportDetails asset={summary} />
        </DetailsPanel>
      );
    const run =
      picked.kind === "origin"
        ? producer
        : picked.kind === "user"
          ? (context.usedBy.find((item) => runKey(item) === picked.key) ?? null)
          : null;
    if (run)
      return (
        <DetailsPanel
          title={runLabel(run)}
          icon={<StatusIcon status={latestExecution(run)?.status ?? null} />}
          openLabel="Open run"
          onOpen={() => openRun(run)}
          onClose={close}
        >
          <RunDetails
            run={run}
            executionId={picked.kind === "origin" ? (origin?.executionId ?? null) : null}
            task={picked.kind === "origin" ? (origin?.task ?? null) : null}
            inputs={picked.kind === "origin" ? context.inputs : undefined}
            onPickInput={(input) => setPicked({ kind: "input", assetId: input.id })}
          />
        </DetailsPanel>
      );
    const input =
      picked.kind === "input"
        ? (context.inputs.find((item) => item.id === picked.assetId) ?? null)
        : null;
    if (input)
      return (
        <DetailsPanel
          title={input.name}
          icon={<AssetKindIcon kind={kindOfAsset(input)} />}
          openLabel="Open asset"
          onOpen={() => openAsset(input)}
          onClose={close}
        >
          <InputDetails asset={input} />
        </DetailsPanel>
      );
    return null;
  })();

  const actions = (
    <>
      {download ? (
        <WorkbenchIconAction label="Download asset" asChild>
          <a href={download} download>
            <Download className="size-icon" />
          </a>
        </WorkbenchIconAction>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal className="size-icon" />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          {reference ? (
            <DropdownMenuItem onSelect={() => copyText(reference, "ref")}>
              Copy ref
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem onSelect={() => copyText(summary.id, "asset id")}>
            Copy asset id
          </DropdownMenuItem>
          {file ? (
            <DropdownMenuItem onSelect={() => copyText(file, "file name")}>
              Copy file name
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <EntityPage icon={Archive} title={summary.name} actions={actions}>
      <div className="relative flex min-h-0 flex-1">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col max-md:overflow-auto">
          <header className="flex flex-none items-center gap-3 px-6 pt-4 pb-3 max-md:px-4">
            <AssetTile kind={kind} />
            <div className="flex min-w-0 flex-col">
              <h1 className="truncate text-title font-semibold">{summary.name}</h1>
              <p className="truncate text-label text-muted-foreground">
                {contextSentence(context, runLabel, citations.data?.length ?? null)}
              </p>
            </div>
          </header>
          <div className="flex-none px-6 pb-4 max-md:px-4">
            {inventory.query.isPending ? (
              <Skeleton
                role="status"
                aria-label="Loading lineage"
                className="h-10 w-full rounded-md"
              />
            ) : (
              <AssetLineage
                inputs={context.inputs.map((input) => ({
                  key: input.id,
                  label: input.name,
                  icon: <AssetKindIcon kind={kindOfAsset(input)} />,
                  selected: samePick(picked, { kind: "input", assetId: input.id }),
                  onClick: () => toggle({ kind: "input", assetId: input.id }),
                }))}
                origin={originNode}
                originTitle={imported ? "Imported from" : "Produced by"}
                self={{
                  key: summary.id,
                  label: summary.name,
                  icon: <AssetKindIcon kind={kind} />,
                  selected: samePick(picked, { kind: "self" }),
                  onClick: () => toggle({ kind: "self" }),
                }}
                usedBy={context.usedBy.map((run) =>
                  runNode(run, { kind: "user", key: runKey(run) }),
                )}
              />
            )}
          </div>
          <div className="flex min-h-0 flex-1 flex-col px-6 pb-6 max-md:min-h-96 max-md:px-4">
            <div className="min-h-0 flex-1 overflow-hidden rounded-md border border-border bg-background">
              <AssetContent asset={summary} kind={kind} mode="full" />
            </div>
          </div>
        </div>
        {panel}
      </div>
    </EntityPage>
  );
};
