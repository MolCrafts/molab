import { Badge, ProgressSpinner } from "@molcrafts/ui";
import type { JSX } from "react";
import { type StatusTone, statusSpec, TONE_FILL } from "@/app/status/vocabulary";
import { cn } from "@/lib/utils";

const TONE_CLASSES: Record<StatusTone, string> = {
  draft: "bg-status-draft/10 text-muted-foreground",
  ready: "bg-status-ready/10 text-status-ready-foreground",
  queued: "bg-status-queued/10 text-foreground",
  running: "bg-status-running-soft text-status-running-foreground hover:bg-status-running-soft",
  completed:
    "bg-status-completed-soft text-status-completed-foreground hover:bg-status-completed-soft",
  failed: "bg-status-failed-soft text-status-failed-foreground hover:bg-status-failed-soft",
  cancelled: "bg-status-cancelled/10 text-muted-foreground",
  cached: "bg-status-cached/10 text-foreground",
  warning: "bg-status-warning-soft text-status-warning-foreground hover:bg-status-warning-soft",
};

const SIZE_CLASSES: Record<StatusBadgeSize, string> = {
  sm: "px-2 py-0 text-micro font-medium",
  md: "px-2 py-1 text-label font-medium",
};

export type StatusBadgeSize = "sm" | "md";

export interface StatusBadgeProps {
  status: string | null | undefined;
  size?: StatusBadgeSize;
  /** Show a leading colored dot (matching tone). Ignored for `running` — that
   *  state always uses a spinning indicator (the single "in progress" affordance). */
  dot?: boolean;
  /** Set false to render only the status indicator without its word. */
  showLabel?: boolean;
  /**
   * The word to print. An execution status passes the vocabulary's word
   * (`RunStatusBadge`); a lifecycle status (a document's `active`, an asset's
   * `archived`) is the owner's own word and is printed as it is.
   */
  word?: string;
}

const sentence = (raw: string): string =>
  raw.charAt(0).toUpperCase() + raw.slice(1).replace(/_/g, " ");

export const StatusBadge = ({
  status,
  size = "md",
  dot = false,
  showLabel = true,
  word,
}: StatusBadgeProps): JSX.Element | null => {
  if (!status) return null;
  const spec = statusSpec(status);
  const tone = spec.tone;
  const label = word ?? sentence(status);
  const isRunning = spec.spin === true;

  if (isRunning) {
    return (
      <Badge
        variant="outline"
        aria-label={showLabel ? undefined : label}
        className={cn(
          TONE_CLASSES.running,
          SIZE_CLASSES[size],
          "inline-flex items-center gap-2",
          size === "sm" ? "px-1" : "px-2",
        )}
      >
        <ProgressSpinner
          className="text-status-running"
          size={size === "sm" ? "sm" : "md"}
          label={label}
        />
        {showLabel && <span>{label}</span>}
      </Badge>
    );
  }

  return (
    <Badge
      variant="outline"
      aria-label={showLabel ? undefined : label}
      className={cn(
        TONE_CLASSES[tone],
        SIZE_CLASSES[size],
        "mol-motion-state inline-flex items-center gap-2",
      )}
    >
      {dot && (
        <span
          aria-hidden="true"
          className={cn("inline-block size-2 rounded-full", TONE_FILL[tone])}
        />
      )}
      {showLabel && <span>{label}</span>}
    </Badge>
  );
};
