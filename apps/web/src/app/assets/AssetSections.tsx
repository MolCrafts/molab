/**
 * The asset page's details panel (L08): what one lineage node is. The page
 * itself shows only the lineage and the preview; a click on a node opens its
 * details here — this asset (file facts, citations), the producing run, a run
 * that uses it, an input asset, or the import source.
 */

import { Skeleton } from "@molcrafts/ui";
import { BookOpen, Copy, ExternalLink, Link2, X } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { StatusIcon } from "@/app/components/entity";
import { formatParameterValue } from "@/app/runs/runTitle";
import type { WorkspaceExecutionRow, WorkspaceRunRow } from "@/app/runs/types";
import type { AssetSummary } from "@/app/types";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";
import { formatDateTime } from "@/lib/datetime";
import { formatBytes } from "@/lib/format-bytes";
import { formatRelative } from "@/lib/format-time";
import { cn } from "@/lib/utils";
import { CountBadge } from "./AssetLineage";
import { ASSET_KIND_META, kindOfAsset } from "./assetKinds";

export const latestExecution = (run: WorkspaceRunRow): WorkspaceExecutionRow | null =>
  [...run.executions].sort((left, right) => left.createdAt.localeCompare(right.createdAt)).at(-1) ??
  null;

export const copyText = (text: string, what: string): void => {
  void navigator.clipboard
    .writeText(text)
    .then(() => toast(`Copied ${what}`))
    .catch(() => toast(`Could not copy ${what}`));
};

// ── parts ────────────────────────────────────────────────────────────────

const Group = ({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: ReactNode;
}): JSX.Element => (
  <section className="flex flex-col gap-1 border-t border-border px-3 py-3 first:border-t-0">
    <h3 className="flex items-center gap-2 text-label font-semibold text-muted-foreground">
      {title}
      {count !== undefined ? <CountBadge count={count} /> : null}
    </h3>
    {children}
  </section>
);

const Fact = ({ label, children }: { label: string; children: ReactNode }): JSX.Element => (
  <div className="flex min-h-list-row items-center gap-3 text-body">
    <span className="w-20 flex-none text-muted-foreground">{label}</span>
    <span className="flex min-w-0 flex-1 items-center">{children}</span>
  </div>
);

const CopyValue = ({
  value,
  shown,
  what,
}: {
  value: string;
  shown?: string;
  what: string;
}): JSX.Element => (
  <span className="flex min-w-0 items-center gap-1" title={value}>
    <span className="truncate font-mono text-label">{shown ?? value}</span>
    <WorkbenchIconAction label={`Copy ${what}`} kind="ghost" onClick={() => copyText(value, what)}>
      <Copy className="size-icon-sm" />
    </WorkbenchIconAction>
  </span>
);

const ParamChip = ({ name, value }: { name: string; value: unknown }): JSX.Element => (
  <span className="inline-flex h-6 items-center gap-1 rounded-sm bg-muted px-2 text-label">
    <span className="text-muted-foreground">{name}</span>
    <span className="font-mono">{formatParameterValue(name, value)}</span>
  </span>
);

const Params = ({ parameters }: { parameters: Record<string, unknown> }): JSX.Element => {
  const entries = Object.entries(parameters);
  return entries.length ? (
    <span className="flex flex-wrap gap-1">
      {entries.map(([name, value]) => (
        <ParamChip key={name} name={name} value={value} />
      ))}
    </span>
  ) : (
    <span className="text-label text-muted-foreground">No parameters.</span>
  );
};

const shortDigest = (digest: string): string => {
  const [algo, hex = ""] = digest.split(":");
  return hex.length > 12 ? `${algo}:${hex.slice(0, 8)}…${hex.slice(-4)}` : digest;
};

// ── the panel frame ──────────────────────────────────────────────────────

export const DetailsPanel = ({
  title,
  icon,
  onOpen,
  openLabel,
  onClose,
  children,
}: {
  title: string;
  icon: ReactNode;
  onOpen?: () => void;
  openLabel?: string;
  onClose: () => void;
  children: ReactNode;
}): JSX.Element => (
  <aside
    aria-label={`${title} details`}
    className={cn(
      "flex min-h-0 w-80 flex-none flex-col border-l border-border bg-background",
      "max-md:absolute max-md:inset-x-0 max-md:bottom-0 max-md:z-20 max-md:max-h-[70%] max-md:w-full max-md:border-t max-md:border-l-0 max-md:shadow-overlay",
    )}
  >
    <div className="flex h-9 flex-none items-center gap-2 border-b border-border pr-1 pl-3">
      {icon}
      <span className="min-w-0 flex-1 truncate text-body font-medium" title={title}>
        {title}
      </span>
      {onOpen ? (
        <WorkbenchIconAction label={openLabel ?? "Open"} kind="ghost" onClick={onOpen}>
          <ExternalLink className="size-icon-sm" />
        </WorkbenchIconAction>
      ) : null}
      <WorkbenchIconAction label="Close details" kind="ghost" onClick={onClose}>
        <X className="size-icon-sm" />
      </WorkbenchIconAction>
    </div>
    <div className="min-h-0 flex-1 overflow-auto">{children}</div>
  </aside>
);

// ── bodies ───────────────────────────────────────────────────────────────

export interface Citation {
  path: string;
  title: string;
  type: string;
  role: string;
}

/** This asset: the file facts and the documents that cite it. */
export const AssetDetails = ({
  asset,
  reference,
  digest,
  file,
  registered,
  citations,
  citationsLoading,
  onOpenCitation,
}: {
  asset: AssetSummary;
  reference: string | null;
  digest: string | null;
  file: string | null;
  registered: string;
  citations: Citation[];
  citationsLoading: boolean;
  onOpenCitation: (path: string) => void;
}): JSX.Element => (
  <>
    <Group title="File">
      <Fact label="Kind">{ASSET_KIND_META[kindOfAsset(asset)].label}</Fact>
      {asset.sizeBytes != null ? <Fact label="Size">{formatBytes(asset.sizeBytes)}</Fact> : null}
      {asset.mediaType ? (
        <Fact label="Type">
          <span className="truncate font-mono text-label">{asset.mediaType}</span>
        </Fact>
      ) : null}
      {reference ? (
        <Fact label="Ref">
          <CopyValue value={reference} what="ref" />
        </Fact>
      ) : null}
      {digest ? (
        <Fact label="Content">
          <CopyValue value={digest} shown={shortDigest(digest)} what="content hash" />
        </Fact>
      ) : null}
      {file ? (
        <Fact label="File">
          <CopyValue value={file} what="file name" />
        </Fact>
      ) : null}
      <Fact label="Registered">
        <span title={formatDateTime(registered)}>{formatRelative(registered)}</span>
      </Fact>
    </Group>
    <Group title="Cited in" count={citations.length}>
      {citationsLoading ? (
        <Skeleton role="status" aria-label="Loading citations" className="h-list-row w-full" />
      ) : citations.length === 0 ? (
        <p className="text-label text-muted-foreground">No knowledge document cites it.</p>
      ) : (
        citations.map((row) => (
          <button
            key={row.path}
            type="button"
            onClick={() => onOpenCitation(row.path)}
            title={`${row.role} · ${row.path}`}
            className="flex min-h-list-row w-full min-w-0 items-center gap-2 rounded-sm text-left text-body hover:bg-interactive"
          >
            <BookOpen aria-hidden className="size-icon-sm flex-none text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate">{row.title}</span>
            <span className="flex-none text-micro text-muted-foreground">{row.type}</span>
          </button>
        ))
      )}
    </Group>
  </>
);

/** A run on the lineage: the producer (with its attempt and task) or a run that uses it. */
export const RunDetails = ({
  run,
  executionId,
  task,
  inputs,
  onPickInput,
}: {
  run: WorkspaceRunRow;
  /** The attempt that registered the asset (the producer); the latest otherwise. */
  executionId?: string | null;
  task?: string | null;
  inputs?: AssetSummary[];
  onPickInput?: (asset: AssetSummary) => void;
}): JSX.Element => {
  const attempt =
    (executionId ? run.executions.find((item) => item.executionId === executionId) : null) ??
    latestExecution(run);
  const when = attempt?.finishedAt ?? attempt?.createdAt ?? run.createdAt;
  return (
    <>
      <Group title="Attempt">
        <Fact label="Status">
          <span className="flex items-center gap-2">
            <StatusIcon status={attempt?.status ?? null} />
            {attempt?.status ?? "not started"}
          </span>
        </Fact>
        {attempt ? (
          <Fact label="Attempt">
            <span className="font-mono text-label">{attempt.executionId}</span>
          </Fact>
        ) : null}
        {task ? (
          <Fact label="Task">
            <span className="font-mono text-label">{task}</span>
          </Fact>
        ) : null}
        <Fact label="When">
          <span title={formatDateTime(when)}>{formatRelative(when)}</span>
        </Fact>
      </Group>
      <Group title="Parameters">
        <Params parameters={run.parameters} />
      </Group>
      <Group title="Where">
        <Fact label="Experiment">
          <span className="truncate">{run.experimentName || run.experimentId}</span>
        </Fact>
        <Fact label="Project">
          <span className="truncate">{run.projectName || run.projectId}</span>
        </Fact>
      </Group>
      {inputs?.length ? (
        <Group title="Inputs" count={inputs.length}>
          {inputs.map((input) => (
            <button
              key={input.id}
              type="button"
              onClick={() => onPickInput?.(input)}
              className="flex min-h-list-row items-center text-left text-body text-accent hover:underline"
            >
              {input.name}
            </button>
          ))}
        </Group>
      ) : null}
    </>
  );
};

/** Another asset on the lineage (an input of the producer). */
export const InputDetails = ({ asset }: { asset: AssetSummary }): JSX.Element => (
  <Group title="Asset">
    <Fact label="Kind">{ASSET_KIND_META[kindOfAsset(asset)].label}</Fact>
    {asset.sizeBytes != null ? <Fact label="Size">{formatBytes(asset.sizeBytes)}</Fact> : null}
    <Fact label="From">
      <span className="truncate">
        {asset.origin?.kind === "execution"
          ? `run ${asset.origin.runId ?? "?"}`
          : asset.origin?.uri || "imported"}
      </span>
    </Fact>
    <Fact label="Registered">{formatRelative(asset.updatedAt)}</Fact>
  </Group>
);

/** The import source, in the producer's place. */
export const ImportDetails = ({ asset }: { asset: AssetSummary }): JSX.Element => (
  <Group title="Imported from">
    <span className="flex min-w-0 items-center gap-2">
      <Link2 aria-hidden className="size-icon-sm flex-none text-muted-foreground" />
      {asset.origin?.uri ? (
        <CopyValue value={asset.origin.uri} what="source" />
      ) : (
        <span className="text-label text-muted-foreground">Not recorded</span>
      )}
    </span>
    <Fact label="Imported">{formatRelative(asset.updatedAt)}</Fact>
  </Group>
);
