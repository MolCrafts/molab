/**
 * What is inside an asset (L08): the image, the first rows of a table, the
 * structure through its file-preview plugin (MolVis), text — or, when nothing
 * can draw it, what it is and how to get it.
 */

import { Button, Skeleton } from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import { type JSX, useMemo } from "react";
import { assetsApi } from "@/api";
import { assetTextQueryOptions, STRUCTURE_PREVIEW_CAP } from "@/app/state/entityQueries";
import type { AssetSummary } from "@/app/types";
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { formatBytes } from "@/lib/format-bytes";
import { AssetTile } from "./AssetTile";
import { ASSET_KIND_META, type AssetKind, assetFileName } from "./assetKinds";
import { parseTablePreview } from "./tablePreview";

/** Text read for a table or a text file; a structure is read whole (up to its cap). */
const TEXT_CAP = 256_000;
const TABLE_ROWS = { thumb: 6, full: 200 } as const;
const TEXT_LINES = { thumb: 14, full: 2_000 } as const;

type Mode = "thumb" | "full";

interface AssetContentProps {
  asset: AssetSummary;
  kind: AssetKind;
  mode: Mode;
}

const Message = ({
  asset,
  kind,
  title,
  detail,
  mode,
}: {
  asset: AssetSummary;
  kind: AssetKind;
  title: string;
  detail: string;
  mode: Mode;
}): JSX.Element => (
  <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
    <AssetTile kind={kind} size={mode === "full" ? "lg" : "md"} />
    <p className="text-body text-foreground">{title}</p>
    <p className="text-label text-muted-foreground">{detail}</p>
    {mode === "full" && asset.projectId ? (
      <Button asChild size="sm" variant="secondary">
        <a href={assetsApi.downloadUrl(asset.projectId, asset.id)} download>
          Download
        </a>
      </Button>
    ) : null}
  </div>
);

const ImageContent = ({ asset }: { asset: AssetSummary }): JSX.Element => (
  <div className="flex h-full items-center justify-center p-2">
    <img
      src={assetsApi.downloadUrl(asset.projectId ?? "", asset.id)}
      alt={asset.name}
      className="max-h-full max-w-full object-contain"
    />
  </div>
);

const TableContent = ({
  name,
  text,
  partial,
  mode,
}: {
  name: string;
  text: string;
  partial: boolean;
  mode: Mode;
}): JSX.Element => {
  const table = useMemo(
    () => parseTablePreview(text, name, TABLE_ROWS[mode], partial),
    [text, name, mode, partial],
  );
  const shown = table.rows.length;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-label">
          <thead className="sticky top-0 bg-surface-subtle">
            <tr>
              {table.header.map((cell, index) => (
                <th
                  // biome-ignore lint/suspicious/noArrayIndexKey: columns are positional
                  key={index}
                  className="border-b border-border px-3 py-1 text-left font-medium whitespace-nowrap"
                >
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: rows are positional
              <tr key={rowIndex} className="even:bg-surface-subtle">
                {row.map((cell, index) => (
                  <td
                    // biome-ignore lint/suspicious/noArrayIndexKey: columns are positional
                    key={index}
                    className="px-3 py-1 font-mono whitespace-nowrap tabular-nums"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="flex-none border-t border-border px-3 py-1 text-micro text-muted-foreground">
        {shown < table.totalRows || table.partial
          ? `First ${shown} of ${table.partial ? "more than " : ""}${table.totalRows.toLocaleString()} rows`
          : `${shown} rows`}
      </p>
    </div>
  );
};

const TextContent = ({ text, mode }: { text: string; mode: Mode }): JSX.Element => {
  const lines = text.split(/\r?\n/).slice(0, TEXT_LINES[mode]);
  return (
    <pre className="h-full overflow-auto p-3 font-mono text-label leading-relaxed whitespace-pre text-foreground">
      {lines.join("\n")}
    </pre>
  );
};

export const AssetContent = ({ asset, kind, mode }: AssetContentProps): JSX.Element => {
  const generation = useContributionGeneration();
  const fileName = assetFileName(asset);
  const plugin = useMemo(() => {
    void generation;
    return filePreviewPluginRegistry.getPluginForFile(fileName, fileName);
  }, [generation, fileName]);
  const cap = kind === "structure" ? STRUCTURE_PREVIEW_CAP : TEXT_CAP;
  const tooLarge = kind === "structure" && (asset.sizeBytes ?? 0) > STRUCTURE_PREVIEW_CAP;
  const readsText =
    Boolean(asset.projectId) &&
    !tooLarge &&
    (kind === "table" ||
      kind === "text" ||
      (kind === "structure" && plugin !== null) ||
      (plugin !== null && kind !== "image"));
  const text = useQuery({
    ...assetTextQueryOptions(asset.projectId ?? "", asset.id, cap),
    enabled: readsText,
  });
  const meta = ASSET_KIND_META[kind];
  const size = asset.sizeBytes != null ? formatBytes(asset.sizeBytes) : null;

  if (!asset.projectId)
    return (
      <Message
        asset={asset}
        kind={kind}
        mode={mode}
        title="No preview"
        detail="This asset has no project to read it from."
      />
    );
  if (kind === "image") return <ImageContent asset={asset} />;
  if (tooLarge)
    return (
      <Message
        asset={asset}
        kind={kind}
        mode={mode}
        title="Too large to preview"
        detail={`${size ?? "This structure"} is past the preview limit. Download it to open it.`}
      />
    );
  if (!readsText)
    return (
      <Message
        asset={asset}
        kind={kind}
        mode={mode}
        title={`No preview for ${meta.label.toLowerCase()}`}
        detail={
          kind === "model"
            ? "Load it with the code that wrote it, or download the bytes."
            : `${asset.mediaType || "These bytes"}${size ? ` · ${size}` : ""}`
        }
      />
    );
  if (text.isPending)
    return (
      <Skeleton role="status" aria-label="Loading preview" className="h-full w-full rounded-none" />
    );
  if (text.error)
    return (
      <Message
        asset={asset}
        kind={kind}
        mode={mode}
        title="Could not read the asset"
        detail={text.error instanceof Error ? text.error.message : String(text.error)}
      />
    );
  const { text: body, partial } = text.data;
  if (kind === "table")
    return <TableContent name={fileName} text={body} partial={partial} mode={mode} />;
  if (plugin) {
    const Preview = plugin.Component;
    return (
      <div className="h-full min-h-0 overflow-hidden">
        <Preview content={body} name={fileName} path={fileName} folderId="" assetId={asset.id} />
      </div>
    );
  }
  return <TextContent text={body} mode={mode} />;
};
