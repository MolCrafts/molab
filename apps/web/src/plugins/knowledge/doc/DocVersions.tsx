/**
 * A knowledge page's git versions (L10): the switcher in the header's class
 * line, the banner over an old version, and that version's diff against the
 * working copy. Versions come from `GET /history/document` (the same read as
 * `molab knowledge versions`); an old version itself is `GET /knowledge/note?version=N`.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { Check, ChevronDown, History } from "lucide-react";
import type { JSX } from "react";
import type { DocumentHistory } from "@/api/generated/models/DocumentHistory";
import { WorkbenchAction } from "@/components/workbench";
import { cn } from "@/lib/utils";
import {
  diffLineTone,
  latestVersion,
  versionAgent,
  versionEvent,
  versionSwitcherLabel,
  versionToOpen,
} from "../knowledgeVersions";
import { useKnowledgeVersionDiffQuery } from "../queries";

const shortDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export interface VersionSwitcherProps {
  history: DocumentHistory;
  /** The version the page shows; null is the live file. */
  viewing: number | null;
  /** Why switching is unavailable (unsaved edits), or null. */
  disabledReason: string | null;
  onSelect: (version: number | null) => void;
}

/** "v3 · latest ▾": every version with its date, event and agent; the working copy when uncommitted. */
export const VersionSwitcher = ({
  history,
  viewing,
  disabledReason,
  onSelect,
}: VersionSwitcherProps): JSX.Element => {
  const label = versionSwitcherLabel(history, viewing);
  const liveIsLatest = !history.uncommitted;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabledReason !== null}>
        <button
          type="button"
          title={disabledReason ?? "Document versions"}
          aria-label={`Document version: ${label}`}
          className="inline-flex h-6 items-center gap-1 rounded-control px-1 text-label text-muted-foreground tabular-nums hover:bg-interactive hover:text-foreground disabled:pointer-events-none disabled:opacity-60"
        >
          <History aria-hidden className="size-icon-sm" />
          {label}
          <ChevronDown aria-hidden className="size-icon-sm" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-80">
        {history.uncommitted ? (
          <>
            <DropdownMenuItem onSelect={() => onSelect(null)} className="justify-between">
              <span className="flex min-w-0 flex-col">
                <span>Working copy</span>
                <span className="text-micro text-muted-foreground">
                  Uncommitted changes since v{latestVersion(history)}
                </span>
              </span>
              {viewing === null ? <Check aria-hidden className="size-icon-sm" /> : null}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        ) : null}
        {history.versions.map((version, index) => {
          const shown = versionToOpen(history, version.number);
          const selected = shown === viewing;
          const agent = versionAgent(version);
          return (
            <DropdownMenuItem
              key={version.commit}
              onSelect={() => onSelect(shown)}
              className="justify-between"
            >
              <span className="flex min-w-0 flex-col">
                <span className="tabular-nums">
                  v{version.number}
                  {index === 0 && liveIsLatest ? " · latest" : ""}
                  <span className="text-muted-foreground"> · {shortDate(version.occurred_at)}</span>
                </span>
                <span className="truncate text-micro text-muted-foreground" title={version.summary}>
                  {versionEvent(version)}
                  {agent ? ` · ${agent}` : ""}
                  {` · ${version.commit.slice(0, 8)}`}
                </span>
              </span>
              {selected ? <Check aria-hidden className="size-icon-sm" /> : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export interface VersionBannerProps {
  history: DocumentHistory | null;
  version: number;
  comparing: boolean;
  onCompare: (comparing: boolean) => void;
  onLatest: () => void;
}

/** Over an old version: what it is, the way back, and the comparison with what is live. */
export const VersionBanner = ({
  history,
  version,
  comparing,
  onCompare,
  onLatest,
}: VersionBannerProps): JSX.Element => {
  const shown = history?.versions.find((item) => item.number === version) ?? null;
  const latest = history ? latestVersion(history) : null;
  const live = history?.uncommitted ? "the working copy" : latest ? `v${latest}` : "the live file";
  return (
    <div
      role="status"
      className="mb-6 flex flex-col gap-1 rounded-control border border-info/30 bg-info-soft px-3 py-2 text-label text-info-foreground"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <History aria-hidden className="size-icon-sm shrink-0" />
        <span className="min-w-0 flex-1 font-medium tabular-nums">
          Viewing v{version}
          {shown ? ` · ${shortDate(shown.occurred_at)}` : ""} — latest is {live}
        </span>
        <WorkbenchAction
          size="compact"
          aria-pressed={comparing}
          onClick={() => onCompare(!comparing)}
        >
          {comparing ? "Show version" : "Compare with latest"}
        </WorkbenchAction>
        <WorkbenchAction size="compact" onClick={onLatest}>
          Back to latest
        </WorkbenchAction>
      </div>
      <p className="text-micro text-muted-foreground">
        Read-only. Figures cited as <code>molab:asset/&lt;id&gt;</code> show the asset's current
        bytes, not the bytes at this version.
      </p>
    </div>
  );
};

const TONE_CLASS = {
  added: "bg-diff-added-soft text-diff-added-foreground",
  removed: "bg-diff-removed-soft text-diff-removed-foreground",
  hunk: "text-muted-foreground",
  context: "",
} as const;

/** Version *version* against the working copy, as a unified diff of the whole file (record included). */
export const VersionDiff = ({
  relPath,
  version,
}: {
  relPath: string;
  version: number;
}): JSX.Element => {
  const query = useKnowledgeVersionDiffQuery(relPath, version);
  if (query.isPending) {
    return <p className="text-body text-muted-foreground italic">Reading the diff…</p>;
  }
  if (query.error) {
    return (
      <p role="alert" className="text-body text-status-failed">
        {query.error instanceof Error ? query.error.message : "Couldn't read the diff."}
      </p>
    );
  }
  const diff = query.data.diff ?? "";
  if (diff === "") {
    return <p className="text-body text-muted-foreground">No changes since v{version}.</p>;
  }
  return (
    <pre className="overflow-x-auto rounded-control border border-border bg-surface py-2 font-mono text-label">
      {diff.split("\n").map((line, index) => (
        <span
          // biome-ignore lint/suspicious/noArrayIndexKey: lines are positions in an immutable diff
          key={index}
          className={cn("block px-3 whitespace-pre", TONE_CLASS[diffLineTone(line)])}
        >
          {line || " "}
        </span>
      ))}
    </pre>
  );
};
