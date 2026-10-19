/** Persistent connection, activity and progress status for the workbench. */

import { Button, Popover, PopoverContent, PopoverTrigger } from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  Check,
  ChevronsLeftRight,
  CloudOff,
  HardDrive,
  Info,
  Loader2,
  RefreshCw,
  Server,
  X,
} from "lucide-react";
import { type JSX, type ReactNode, useEffect, useRef, useState } from "react";
import { getWorkspaceQueryScope } from "@/app/state/workspaceSwitchEvents";
import type { ServedWorkspaceSummary } from "@/app/types";
import { useStatusMessage } from "@/hooks/useStatusMessage";
import { reportStatus, type StatusReportType } from "@/lib/status-report";
import { cn } from "@/lib/utils";
import { parseHostQualifiedLabel } from "@/lib/workspace-path";
import { WorkbenchIconAction } from "./WorkbenchAction";

export interface WorkbenchStatusStripProps {
  className?: string;
  isRefreshing?: boolean;
  /**
   * Called once when a remote index walk finishes (phase → done) so the
   * shell can re-fetch projects after a background link/refresh.
   */
  onRemoteIndexReady?: () => void;
  /** Active served workspace for the connection-status popover. */
  activeWorkspace?: ServedWorkspaceSummary | null;
  /**
   * Reconnect / re-auth (remote OTP) or hard refresh. Icon-only control in
   * the connection popover — no label text.
   */
  onReconnect?: () => void;
  /** Right-aligned plugin status-bar items. */
  extras?: ReactNode;
}

interface CacheStatus {
  cached: boolean;
  ready?: boolean | null;
  indexing?: boolean | null;
  phase: string;
  total: number;
  done: number;
  percent: number | null;
  message: string;
}

function ActivityIcon({
  type,
  progress,
  running,
}: {
  type: StatusReportType;
  progress?: number;
  running?: boolean;
}): JSX.Element {
  const className = "size-3 shrink-0";
  if (type === "error") {
    return <AlertCircle className={cn(className, "text-statusbar-foreground")} />;
  }
  if (type === "warning") {
    return <AlertTriangle className={cn(className, "text-statusbar-foreground")} />;
  }
  if (type === "success") {
    return <Check className={cn(className, "text-statusbar-foreground")} />;
  }
  if (progress !== undefined || running) {
    return (
      <Loader2 className={cn(className, "mol-motion-progress-spin text-statusbar-foreground")} />
    );
  }
  return <Info className={cn(className, "text-statusbar-foreground")} />;
}

function activityTextClass(type: StatusReportType): string {
  void type;
  return "text-statusbar-foreground";
}

/**
 * Loading progress track.
 * - *percent* set → determinate fill
 * - otherwise → indeterminate shimmer (counting / generic sync)
 */
function ProgressTrack({
  percent,
  indeterminate,
}: {
  percent?: number;
  indeterminate?: boolean;
}): JSX.Element {
  const clamped =
    percent !== undefined && Number.isFinite(percent)
      ? Math.max(0, Math.min(100, percent))
      : undefined;

  return (
    <div
      className="relative h-1 min-w-22 max-w-48 flex-1 overflow-hidden rounded-full bg-statusbar-foreground/25 sm:min-w-32"
      role="progressbar"
      aria-valuenow={clamped !== undefined ? Math.round(clamped) : undefined}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-busy={indeterminate || clamped === undefined}
    >
      {clamped !== undefined && !indeterminate ? (
        <div
          className="h-full rounded-full bg-statusbar-foreground transition-[width] duration-150 ease-out"
          style={{ width: `${clamped}%` }}
        />
      ) : (
        <div className="mol-status-progress-indeterminate h-full w-1/3 rounded-full bg-statusbar-foreground/90" />
      )}
    </div>
  );
}

function isRemoteIndexing(body: CacheStatus | null): boolean {
  if (!body?.cached) return false;
  // "counting" kept for back-compat with older servers; current code skips it.
  return body.phase === "counting" || body.phase === "fetching" || body.indexing === true;
}

function connectionHeadline(args: {
  busy: boolean;
  unreachable: boolean;
  needsAuth: boolean;
  hasWorkspace: boolean;
}): {
  label: string;
  tone: string;
} {
  if (args.needsAuth) {
    return { label: "Verification code", tone: "text-status-warning-foreground" };
  }
  if (args.unreachable) {
    return { label: "Unreachable", tone: "text-status-failed-foreground" };
  }
  if (args.busy) {
    return { label: "Syncing", tone: "text-status-running-foreground" };
  }
  if (!args.hasWorkspace) {
    return { label: "No workspace", tone: "text-muted-foreground" };
  }
  return { label: "Connected", tone: "text-status-completed-foreground" };
}

export const WorkbenchStatusStrip = ({
  className,
  isRefreshing = false,
  onRemoteIndexReady,
  activeWorkspace = null,
  onReconnect,
  extras,
}: WorkbenchStatusStripProps): JSX.Element => {
  const { activity, dismissActivity } = useStatusMessage();
  const cacheQuery = useQuery({
    queryKey: ["remote-cache-status", getWorkspaceQueryScope(), activeWorkspace?.key],
    enabled: Boolean(activeWorkspace?.isRemote && !activeWorkspace.unreachable),
    queryFn: async ({ signal }) => {
      const response = await fetch("/api/workspace/cache/status", { signal });
      if (!response.ok) throw new Error(`Remote index unavailable (${response.status})`);
      return (await response.json()) as CacheStatus;
    },
    refetchInterval: (query) =>
      query.state.status !== "error" && isRemoteIndexing(query.state.data ?? null) ? 200 : 2000,
    refetchIntervalInBackground: false,
  });
  const cacheStatus =
    !cacheQuery.isError && !activeWorkspace?.unreachable && cacheQuery.data?.cached
      ? cacheQuery.data
      : null;
  const [statusOpen, setStatusOpen] = useState(false);
  const wasIndexing = useRef(false);
  const lastReportedPhase = useRef<string>("");

  // Only reporting is an effect; Query owns fetching, cancellation and visibility.
  useEffect(() => {
    const body = cacheStatus;
    const active = isRemoteIndexing(body) && !cacheQuery.isError && !activeWorkspace?.unreachable;
    if (active && body) {
      const percent = body.percent ?? (body.total > 0 ? (100 * body.done) / body.total : 0);
      const signature = `${body.phase}:${body.done}:${body.total}:${percent}`;
      if (signature !== lastReportedPhase.current) {
        lastReportedPhase.current = signature;
        reportStatus(body.message || "Syncing remote tree…", "info", percent);
      }
    } else if (wasIndexing.current) {
      lastReportedPhase.current = "";
      if (body?.phase === "done" && !cacheQuery.isError) {
        reportStatus("Remote index ready", "success");
        onRemoteIndexReady?.();
      } else {
        reportStatus(body?.message || "Remote indexing stopped", "warning");
      }
    }
    wasIndexing.current = active;
  }, [cacheStatus, cacheQuery.isError, activeWorkspace?.unreachable, onRemoteIndexReady]);

  // Generic workspace bootstrap / manual refresh — keep the strip busy for the
  // full fetch. progress=0 is sticky in the status bus; the strip maps 0 →
  // indeterminate so the bar shimmers instead of freezing as a zero-width fill.
  const wasRefreshing = useRef(false);
  useEffect(() => {
    if (isRemoteIndexing(cacheStatus)) {
      // Remote index owns the line — keep refresh edge tracking in sync so we
      // don't fire a stale "ready" tip when the local fetch ends mid-index.
      wasRefreshing.current = isRefreshing;
      return;
    }
    if (isRefreshing) {
      if (!wasRefreshing.current) {
        // progress=0 keeps the tip sticky (no 5s auto-clear); strip treats 0
        // as indeterminate so the bar shimmers instead of freezing at 0%.
        reportStatus("Loading workspace…", "info", 0);
      }
      wasRefreshing.current = true;
      return;
    }
    if (wasRefreshing.current) {
      wasRefreshing.current = false;
      // Replace the bootstrap tip (auto-clears). Avoid dismissActivity — it
      // would also wipe an unrelated warning/error that landed mid-refresh.
      reportStatus("Workspace ready", "success");
    }
  }, [isRefreshing, cacheStatus]);

  const remoteBusy = isRemoteIndexing(cacheStatus);
  const remotePercent: number | undefined = (() => {
    if (!remoteBusy || !cacheStatus) return undefined;
    if (cacheStatus.phase === "counting") return undefined; // indeterminate
    if (cacheStatus.percent != null && Number.isFinite(cacheStatus.percent)) {
      return cacheStatus.percent;
    }
    if (cacheStatus.total > 0) {
      return (100 * cacheStatus.done) / cacheStatus.total;
    }
    return undefined;
  })();

  const hasBusActivity = activity.text.length > 0;
  const showRemote = remoteBusy;
  const showSyncing = isRefreshing && !remoteBusy;
  const loading = showRemote || showSyncing;

  // Prefer live bus text (includes reportStatus progress suffix); fall back
  // to remote message / generic syncing.
  const lineText = hasBusActivity
    ? activity.text
    : showRemote
      ? cacheStatus?.message ||
        (cacheStatus?.phase === "counting"
          ? "Counting remote files…"
          : cacheStatus && cacheStatus.total > 0
            ? `Syncing remote tree (${cacheStatus.done}/${cacheStatus.total})…`
            : "Syncing remote tree…")
      : showSyncing
        ? "Loading workspace…"
        : "";

  const lineType: StatusReportType = hasBusActivity
    ? activity.type
    : cacheStatus?.phase === "error"
      ? "error"
      : "info";

  // Determinate only when we know a real percent; counting / generic load →
  // indeterminate. Treat progress 0 as "started, unknown fraction" so the bar
  // never freezes as a zero-width determinate fill.
  const rawProgress: number | undefined = hasBusActivity ? activity.progress : remotePercent;
  const lineProgress: number | undefined =
    rawProgress !== undefined && rawProgress > 0 ? rawProgress : undefined;

  const showProgressTrack = loading || lineProgress !== undefined;
  const indeterminate =
    loading &&
    (lineProgress === undefined ||
      cacheStatus?.phase === "counting" ||
      (showSyncing && !remoteBusy));

  const isAlert = hasBusActivity && (activity.type === "error" || activity.type === "warning");
  const busy = Boolean(isRefreshing || remoteBusy);
  const unreachable = Boolean(activeWorkspace?.unreachable);
  const needsAuth = Boolean(activeWorkspace?.needsAuth);
  const connection = connectionHeadline({
    busy,
    unreachable,
    needsAuth,
    hasWorkspace: Boolean(activeWorkspace),
  });
  const WorkspaceIcon = unreachable ? CloudOff : activeWorkspace?.isRemote ? Server : HardDrive;

  const host = activeWorkspace ? parseHostQualifiedLabel(activeWorkspace.label)?.host : null;
  const connectionLabel = activeWorkspace?.isRemote
    ? `SSH: ${host ?? "Remote"}`
    : activeWorkspace
      ? "Local"
      : "Open folder";

  return (
    <div
      className={cn(
        "flex h-6 shrink-0 items-center border-t border-border bg-statusbar text-statusbar-foreground",
        className,
      )}
    >
      <div className="flex h-full min-w-0 shrink-0 items-center">
        <Popover open={statusOpen} onOpenChange={setStatusOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              className="h-full max-w-52 gap-2 rounded-none border-0 bg-accent px-2 text-micro text-accent-foreground hover:bg-accent-hover hover:text-accent-foreground"
              aria-label={`${connectionLabel} — ${connection.label}. Connection status`}
              title={`${connectionLabel} — ${connection.label}`}
            >
              {unreachable ? (
                <CloudOff className="size-3.5 shrink-0" aria-hidden />
              ) : activeWorkspace?.isRemote ? (
                <ChevronsLeftRight className="size-3.5 shrink-0" aria-hidden />
              ) : (
                <HardDrive className="size-3.5 shrink-0" aria-hidden />
              )}
              <span className="truncate">{connectionLabel}</span>
              {needsAuth ? <AlertTriangle className="size-3 shrink-0" aria-hidden /> : null}
            </Button>
          </PopoverTrigger>
          <PopoverContent side="top" align="start" sideOffset={8} className="w-64 p-2">
            <div className="flex min-w-0 items-center gap-2">
              <WorkspaceIcon
                className={cn(
                  "size-icon-sm flex-none",
                  unreachable
                    ? "text-status-failed-foreground"
                    : activeWorkspace?.isRemote
                      ? "text-status-warning-foreground"
                      : "text-muted-foreground",
                )}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs text-foreground" title={activeWorkspace?.label}>
                  {connectionLabel}
                </p>
                <p className={cn("text-micro", connection.tone)}>{connection.label}</p>
              </div>
              {onReconnect ? (
                <WorkbenchIconAction
                  label={
                    needsAuth ? "Enter verification code" : unreachable ? "Reconnect" : "Reload"
                  }
                  onClick={() => {
                    setStatusOpen(false);
                    onReconnect();
                  }}
                >
                  <RefreshCw className="size-icon-sm" aria-hidden />
                </WorkbenchIconAction>
              ) : null}
            </div>
            {activeWorkspace ? (
              <p className="mt-2 break-all border-t border-border pt-2 text-micro text-muted-foreground">
                {parseHostQualifiedLabel(activeWorkspace.label)?.root ?? activeWorkspace.label}
              </p>
            ) : null}
          </PopoverContent>
        </Popover>
      </div>
      <div
        role="status"
        aria-live={lineType === "error" ? "assertive" : "polite"}
        className="flex h-full min-w-0 flex-1 items-center gap-2 overflow-hidden px-2 font-mono text-micro tabular-nums"
      >
        {lineText && isAlert ? (
          <div
            key={activity.pulse}
            className="flex min-w-0 max-w-[55%] items-center gap-1 overflow-hidden sm:max-w-[60%]"
          >
            <div className="flex min-w-0 items-center gap-2 overflow-hidden" title={lineText}>
              <ActivityIcon type={lineType} progress={lineProgress} />
              <span className={cn("min-w-0 truncate leading-none", activityTextClass(lineType))}>
                {lineText}
              </span>
            </div>
            <WorkbenchIconAction
              label="Dismiss status"
              size="compact"
              className="shrink-0 text-statusbar-foreground hover:bg-statusbar-foreground/15 hover:text-statusbar-foreground"
              onClick={dismissActivity}
            >
              <X className="size-3" aria-hidden />
            </WorkbenchIconAction>
          </div>
        ) : lineText ? (
          <div
            key={
              hasBusActivity
                ? activity.pulse
                : showRemote
                  ? `remote-${cacheStatus?.phase}`
                  : "syncing"
            }
            className="flex min-w-0 max-w-[55%] items-center gap-2 overflow-hidden sm:max-w-[60%]"
            title={lineText}
          >
            <ActivityIcon type={lineType} progress={lineProgress} running={loading} />
            <span className={cn("min-w-0 truncate leading-none", activityTextClass(lineType))}>
              {lineText}
            </span>
          </div>
        ) : (
          <div className="min-w-0 max-w-[40%]" />
        )}

        {showProgressTrack ? (
          <ProgressTrack percent={lineProgress} indeterminate={indeterminate} />
        ) : null}

        {/* Explicit fraction when we have totals (easier to read than % alone). */}
        {remoteBusy && cacheStatus && cacheStatus.total > 0 && cacheStatus.phase !== "counting" ? (
          <span className="shrink-0 font-mono text-micro tabular-nums text-statusbar-foreground/80">
            {cacheStatus.done}/{cacheStatus.total}
          </span>
        ) : lineProgress !== undefined && !indeterminate ? (
          <span className="shrink-0 font-mono text-micro tabular-nums text-statusbar-foreground/80">
            {Math.round(lineProgress)}%
          </span>
        ) : null}
      </div>
      {extras ? <div className="flex shrink-0 items-center gap-1 px-1">{extras}</div> : null}
    </div>
  );
};
