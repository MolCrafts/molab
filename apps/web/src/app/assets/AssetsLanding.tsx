/**
 * `/assets` (L08 v3): every asset in its context — under the experiment and
 * the run that produced it, imports under Imported with where they came
 * from. A row previews on click and opens on double-click or Enter. Group by
 * is an icon menu; Import asset is the one button.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { useQueries } from "@tanstack/react-query";
import { BookOpen, Check, FlaskConical, Group, Link2, Upload } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import { usePermissions } from "@/app/auth";
import { StatusIcon } from "@/app/components/entity";
import { useScopeRuns } from "@/app/dashboard/useScopeRuns";
import type { NavigationLandingProps } from "@/app/navigation/sections";
import { usePreview } from "@/app/preview/PreviewContext";
import { runLabel, withRunTitles } from "@/app/runs/runTitle";
import { EditorActions } from "@/app/shell/editorActions";
import type { AssetSummary } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { WorkbenchIconAction, WorkbenchOperationState } from "@/components/workbench";
import { formatBytes } from "@/lib/format-bytes";
import { formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";
import { assetCitationsQueryOptions } from "@/plugins/knowledge/queries";
import { CountBadge } from "./AssetLineage";
import { latestExecution } from "./AssetSections";
import { AssetKindIcon } from "./AssetTile";
import {
  type AssetBlock,
  type AssetGroup,
  type AssetGrouping,
  groupAssets,
  usersOf,
} from "./assetContext";
import { kindOfAsset } from "./assetKinds";
import { ImportAssetDialog } from "./ImportAssetDialog";

const GROUPINGS: { value: AssetGrouping; label: string }[] = [
  { value: "experiment", label: "Experiment" },
  { value: "project", label: "Project" },
  { value: "kind", label: "Kind" },
  { value: "none", label: "None" },
];

const GroupMenu = ({
  value,
  onChange,
}: {
  value: AssetGrouping;
  onChange: (value: AssetGrouping) => void;
}): JSX.Element => (
  <DropdownMenu>
    <DropdownMenuTrigger asChild>
      <WorkbenchIconAction label={`Group by ${value}`}>
        <Group className="size-icon" />
      </WorkbenchIconAction>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-44">
      {GROUPINGS.map((option) => (
        <DropdownMenuItem key={option.value} onSelect={() => onChange(option.value)}>
          <span className="flex-1">{option.label}</span>
          {option.value === value ? <Check aria-hidden className="size-icon-sm" /> : null}
        </DropdownMenuItem>
      ))}
    </DropdownMenuContent>
  </DropdownMenu>
);

interface RowProps {
  asset: AssetSummary;
  used: number;
  cited: number;
  indent: boolean;
  previewed: boolean;
  onPreview: (asset: AssetSummary) => void;
  onOpen: (asset: AssetSummary) => void;
}

const AssetRow = ({
  asset,
  used,
  cited,
  indent,
  previewed,
  onPreview,
  onOpen,
}: RowProps): JSX.Element => (
  <button
    type="button"
    onClick={() => onPreview(asset)}
    onDoubleClick={() => onOpen(asset)}
    onKeyDown={(event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        onOpen(asset);
      }
    }}
    className={cn(
      "grid h-list-row w-full grid-cols-[minmax(0,16rem)_5rem_minmax(0,10rem)_minmax(0,10rem)_1fr] items-center gap-3 pr-3 text-left text-body hover:bg-interactive focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring max-md:grid-cols-[minmax(0,1fr)_5rem]",
      indent ? "pl-12 max-md:pl-6" : "pl-6 max-md:pl-2",
      previewed && "bg-accent-muted",
    )}
  >
    <span className="flex min-w-0 items-center gap-2">
      <AssetKindIcon kind={kindOfAsset(asset)} />
      <span className="truncate">{asset.name}</span>
    </span>
    <span className="text-right text-label tabular-nums text-muted-foreground">
      {asset.sizeBytes != null ? formatBytes(asset.sizeBytes) : "—"}
    </span>
    <span className="flex min-w-0 items-center gap-1 text-label text-muted-foreground max-md:hidden">
      {used ? (
        <>
          <FlaskConical aria-hidden className="size-icon-sm flex-none" />
          used by {used} run{used === 1 ? "" : "s"}
        </>
      ) : (
        "not used yet"
      )}
    </span>
    <span className="flex min-w-0 items-center gap-1 text-label text-muted-foreground max-md:hidden">
      {cited ? (
        <>
          <BookOpen aria-hidden className="size-icon-sm flex-none" />
          cited in {cited}
        </>
      ) : null}
    </span>
    <span className="max-md:hidden" />
  </button>
);

const BlockHead = ({ block }: { block: AssetBlock }): JSX.Element | null => {
  if (block.run) {
    const attempt = latestExecution(block.run);
    return (
      <div className="flex h-list-row min-w-0 items-center gap-2 pl-6 text-body max-md:pl-2">
        <StatusIcon status={attempt?.status ?? null} />
        <span className="truncate font-mono">{runLabel(block.run)}</span>
        <span className="flex-none text-micro text-muted-foreground">
          {[attempt?.executionId, formatRelative(attempt?.createdAt ?? block.run.createdAt)]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </div>
    );
  }
  if (!block.source) return null;
  return (
    <div className="flex h-list-row min-w-0 items-center gap-2 pl-6 text-body max-md:pl-2">
      <Link2 aria-hidden className="size-icon-sm flex-none text-muted-foreground" />
      <span className="truncate font-mono">{block.source}</span>
    </div>
  );
};

const GroupHead = ({ group }: { group: AssetGroup }): JSX.Element | null =>
  group.kind === "all" ? null : (
    <h2 className="mt-3 flex h-list-row items-center gap-2 border-b border-border text-label font-medium first:mt-0">
      {group.kind === "imported" ? (
        <Link2 aria-hidden className="size-icon-sm text-muted-foreground" />
      ) : (
        <FlaskConical aria-hidden className="size-icon-sm text-muted-foreground" />
      )}
      <span className="font-semibold">{group.title}</span>
      {group.where ? <span className="text-label text-muted-foreground">{group.where}</span> : null}
      <CountBadge count={group.count} />
    </h2>
  );

export const AssetsLanding = ({ snapshot, onRefresh }: NavigationLandingProps): JSX.Element => {
  const [grouping, setGrouping] = useState<AssetGrouping>("experiment");
  const [importOpen, setImportOpen] = useState(false);
  const { writeDeniedReason } = usePermissions();
  const preview = usePreview();
  const inventory = useScopeRuns({}, true);
  const runs = useMemo(() => withRunTitles(inventory.rows), [inventory.rows]);
  const assets = useMemo(
    () => [...new Map(snapshot.assets.map((asset) => [asset.id, asset])).values()],
    [snapshot.assets],
  );
  const groups = useMemo(
    () =>
      groupAssets(
        assets,
        runs,
        grouping,
        (id) => snapshot.projects.find((project) => project.id === id)?.name ?? id,
      ),
    [assets, runs, grouping, snapshot.projects],
  );
  const citations = useQueries({
    queries: assets.map((asset) => assetCitationsQueryOptions(asset.id)),
  });
  const cited = new Map(
    assets.map((asset, index) => [asset.id, citations[index]?.data?.length ?? 0]),
  );

  const onPreview = (asset: AssetSummary): void =>
    preview.preview({ kind: "asset", assetId: asset.id });
  const onOpen = (asset: AssetSummary): void => preview.open({ kind: "asset", assetId: asset.id });

  return (
    <section aria-label="Assets" className="flex h-full min-h-0 flex-col bg-background">
      <EditorActions>
        <div className="flex items-center gap-1">
          <GroupMenu value={grouping} onChange={setGrouping} />
          <DialogButton
            size="chrome"
            kind="primary"
            disabled={Boolean(writeDeniedReason) || snapshot.projects.length === 0}
            title={writeDeniedReason ?? undefined}
            onClick={() => setImportOpen(true)}
          >
            Import asset
          </DialogButton>
        </div>
      </EditorActions>
      <div className="min-h-0 flex-1 overflow-auto px-6 py-3 max-md:px-3">
        {assets.length === 0 ? (
          <WorkbenchOperationState
            kind="empty"
            title="No assets yet"
            detail="A run registers the files worth citing; import a file to bring one in."
            action={
              <WorkbenchIconAction label="Import asset" onClick={() => setImportOpen(true)}>
                <Upload className="size-icon" />
              </WorkbenchIconAction>
            }
          />
        ) : (
          groups.map((group) => (
            <div key={group.key} className="flex flex-col">
              <GroupHead group={group} />
              {group.blocks.map((block) => (
                <div key={block.key} className="flex flex-col">
                  {group.kind === "all" ? null : <BlockHead block={block} />}
                  {block.assets.map((asset) => (
                    <AssetRow
                      key={asset.id}
                      asset={asset}
                      used={usersOf(asset.id, runs).length}
                      cited={cited.get(asset.id) ?? 0}
                      indent={group.kind !== "all" && Boolean(block.run || block.source)}
                      previewed={preview.isPreviewed({ kind: "asset", assetId: asset.id })}
                      onPreview={onPreview}
                      onOpen={onOpen}
                    />
                  ))}
                </div>
              ))}
            </div>
          ))
        )}
      </div>
      <ImportAssetDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        projects={snapshot.projects}
        onImported={onRefresh}
      />
    </section>
  );
};
