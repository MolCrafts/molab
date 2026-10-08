import { WorkbenchAction, WorkbenchIconAction, WorkbenchTag } from "@/components/workbench";
// ─────────────────────────────────────────────────────────────────────────────
// Dashboard primitives — section / chart vocabulary for entity Overviews.
// Shared by Project / Experiment / Run so hierarchy pages share one surface
// language (canvas shell + mono section headers + hairline borders). Pure
// presentation only; no shadcn Card layout wrappers.
// ─────────────────────────────────────────────────────────────────────────────

import { Check, Copy, type LucideIcon } from "lucide-react";
import { type JSX, type ReactNode, useId, useState } from "react";

import { STATUS_GROUPS } from "@/app/runs/statusGroups";
import { cn } from "@/lib/utils";

/** Minimal status rollup shape (mirrors RunStatusCounts without importing it). */
export interface StatusCountRollup {
  total: number;
  running: number;
  pending: number;
  succeeded: number;
  failed: number;
  cancelled: number;
}

// ── MetaField ────────────────────────────────────────────────────────────────

interface MetaFieldProps {
  label: string;
  value: ReactNode;
  /** Monospace value (ids, hashes, raw params). */
  mono?: boolean;
  className?: string;
  title?: string;
  /** Raw value copied by the always-visible copy affordance. */
  copyValue?: string;
}

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

/** Compact, reusable copy control for dense scientific data surfaces. */
export const CopyButton = ({ value, label = "value", className }: CopyButtonProps): JSX.Element => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async (): Promise<void> => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  const Icon = copied ? Check : Copy;
  return (
    <WorkbenchIconAction
      label={copied ? `${label} copied` : `Copy ${label}`}
      className={cn("size-6 text-muted-foreground", copied && "text-success", className)}
      onClick={(event) => {
        event.stopPropagation();
        void handleCopy();
      }}
    >
      <Icon className="size-3" aria-hidden />
    </WorkbenchIconAction>
  );
};

/** One labeled field on a dashboard — sentence-case label, quiet hierarchy. */
export const MetaField = ({
  label,
  value,
  mono = false,
  className,
  title,
  copyValue,
}: MetaFieldProps): JSX.Element => (
  <div className={cn("min-w-0", className)}>
    <dt className="font-mono text-micro uppercase tracking-wider text-muted-foreground">{label}</dt>
    <dd
      className={cn(
        "mt-1 flex min-w-0 items-center gap-1 text-body text-foreground",
        mono && "font-mono text-label",
      )}
      title={title}
    >
      <span className="min-w-0 truncate">{value}</span>
      {copyValue !== undefined && <CopyButton value={copyValue} label={label} />}
    </dd>
  </div>
);

// ── OverviewSurface ──────────────────────────────────────────────────────────

interface OverviewSurfaceProps {
  children: ReactNode;
  className?: string;
  /** Extra classes on the fill surface. */
  surfaceClassName?: string;
}

/**
 * Entity work surface shell. Solid background (no instrumentation grid).
 * Inventory tabs fill height; Overview dashboards scroll with air.
 */
export const OverviewSurface = ({
  children,
  className,
  surfaceClassName,
}: OverviewSurfaceProps): JSX.Element => (
  <div
    className={cn(
      "molab-dashboard flex min-h-0 flex-1 flex-col overflow-auto bg-background",
      className,
    )}
  >
    <div className={cn("min-h-0 min-w-0 flex-1", surfaceClassName)}>{children}</div>
  </div>
);

/**
 * Padded, max-width canvas — Overview posture and inventory tabs share this air.
 */
export const DashboardCanvas = ({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}): JSX.Element => (
  <div className={cn("mx-auto w-full max-w-6xl space-y-6 px-4 py-4 md:px-6", className)}>
    {children}
  </div>
);

/**
 * Inventory tab body: same padding language as Overview, wider for tables.
 * Full-height tables pass ``fill`` and put the table in a flex child.
 */
export const InventoryCanvas = ({
  children,
  className,
  fill = false,
}: {
  children: ReactNode;
  className?: string;
  /** Stretch to fill the tab (for DataTable tabs). */
  fill?: boolean;
}): JSX.Element => (
  <div
    className={cn(
      fill
        ? "flex h-full min-h-0 w-full flex-col px-4 pt-4 md:px-6 md:pt-4"
        : "mx-auto w-full max-w-6xl space-y-6 px-6 py-6 md:px-8 md:py-8",
      className,
    )}
  >
    {children}
  </div>
);

// ── DashboardCard ────────────────────────────────────────────────────────────

interface DashboardCardProps {
  title?: ReactNode;
  /** Quiet secondary line under the title — prefer short counts, not prose. */
  description?: ReactNode;
  /** Right-aligned header slot — a count, a control, a link. */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  /** Soft destructive surface for error banners. */
  variant?: "default" | "destructive";
  /** Optional section glyph (Run overview style). */
  icon?: LucideIcon;
  /** Optional count badge in the section header. */
  count?: number;
  /** Copy payload for the header copy control. */
  copyText?: string;
  copyLabel?: string;
}

/**
 * Quiet section on a full-bleed work surface.
 * Toolbar-height label row — no accent gradients, no card chrome.
 */
export const DashboardCard = ({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
  variant = "default",
  icon: Icon,
  count,
  copyText,
  copyLabel,
}: DashboardCardProps): JSX.Element => {
  const headingId = useId();
  const hasHeader =
    title != null || action != null || count !== undefined || copyText !== undefined;

  return (
    <section
      aria-labelledby={title != null ? headingId : undefined}
      aria-label={typeof title === "string" ? title : undefined}
      className={cn(
        "flex min-w-0 flex-col",
        variant === "destructive" && "bg-status-failed-soft",
        className,
      )}
    >
      {hasHeader && (
        <header className="flex h-control-compact items-center gap-2 border-b border-border px-3">
          {Icon != null && (
            <Icon
              className={cn(
                "size-icon-sm shrink-0 text-muted-foreground",
                variant === "destructive" && "text-status-failed",
              )}
              aria-hidden
            />
          )}
          {title != null && (
            <h3
              id={headingId}
              className={cn(
                "min-w-0 truncate text-label font-medium text-foreground",
                variant === "destructive" && "text-status-failed-foreground",
              )}
            >
              {title}
            </h3>
          )}
          {count !== undefined && (
            <span className="font-mono text-micro tabular-nums text-muted-foreground">{count}</span>
          )}
          {description != null && (
            <span className="hidden min-w-0 truncate text-micro text-muted-foreground sm:inline">
              {description}
            </span>
          )}
          <div className="ml-auto flex shrink-0 items-center gap-1">
            {copyText !== undefined && (
              <CopyButton
                value={copyText}
                label={copyLabel ?? String(title ?? "section")}
                className="size-4-lg"
              />
            )}
            {action}
          </div>
        </header>
      )}
      <div className={cn("min-w-0", bodyClassName ?? "px-3 py-2")}>{children}</div>
    </section>
  );
};

// ── Status distribution ──────────────────────────────────────────────────────

interface StatusDistributionProps {
  counts: StatusCountRollup;
  /** Show the legend list under the bar. Default true. */
  legend?: boolean;
  /** Noun for the accessible total. Default "runs". */
  unit?: string;
  className?: string;
}

/** Segmented status bar + optional legend — shared by project / experiment. */
export const StatusDistribution = ({
  counts,
  legend = true,
  unit = "runs",
  className,
}: StatusDistributionProps): JSX.Element => {
  const empty = counts.total === 0;

  return (
    <div className={cn("space-y-2", className)}>
      <div
        className="flex h-1.5 overflow-hidden rounded-control bg-muted"
        role="img"
        aria-label={empty ? `No ${unit}` : `Status mix across ${counts.total} ${unit}`}
      >
        {!empty &&
          STATUS_GROUPS.map((group) => {
            const value = counts[group.id];
            if (value === 0) return null;
            return (
              <div
                key={group.id}
                title={`${group.label}: ${value}`}
                className="h-full min-w-hairline transition-[width]"
                style={{
                  width: `${(value / counts.total) * 100}%`,
                  backgroundColor: group.color,
                }}
              />
            );
          })}
      </div>
      {legend && (
        <ul className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          {STATUS_GROUPS.map((group) => {
            const value = counts[group.id];
            return (
              <li key={group.id} className="flex items-center justify-between gap-2 text-label">
                <span className="inline-flex min-w-0 items-center gap-2 text-muted-foreground">
                  <span
                    aria-hidden="true"
                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ backgroundColor: group.color }}
                  />
                  <span className="truncate">{group.label}</span>
                </span>
                <span
                  className={cn(
                    "font-medium tabular-nums text-foreground",
                    value === 0 && "text-muted-foreground/50",
                  )}
                >
                  {value}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

// ── Breadcrumb trail (inline entity path) ────────────────────────────────────

interface EntityPathSegment {
  label: string;
  onClick?: () => void;
}

interface EntityPathProps {
  segments: EntityPathSegment[];
  trailing?: ReactNode;
  className?: string;
}

/** Quiet project / experiment / workflow path under a summary card. */
export const EntityPath = ({ segments, trailing, className }: EntityPathProps): JSX.Element => (
  <div
    className={cn(
      "flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-border/60 pt-3 text-label text-muted-foreground",
      className,
    )}
  >
    {segments.map((seg, i) => {
      // Stable path key from the prefix labels (unique within a breadcrumb).
      const pathKey = segments
        .slice(0, i + 1)
        .map((s) => s.label)
        .join("/");
      return (
        <span key={pathKey} className="inline-flex items-center gap-2">
          {i > 0 && <span className="text-border">/</span>}
          {seg.onClick ? (
            <WorkbenchAction
              kind="ghost"
              size="content"
              type="button"
              className="truncate hover:text-foreground hover:underline"
              onClick={seg.onClick}
            >
              {seg.label}
            </WorkbenchAction>
          ) : (
            <span className="truncate">{seg.label}</span>
          )}
        </span>
      );
    })}
    {trailing != null && <span className="ml-auto font-mono text-micro">{trailing}</span>}
  </div>
);

// ── Chip / tag ───────────────────────────────────────────────────────────────

interface ParamChipProps {
  /** Optional key; omit for bare value chips in a labeled axis row. */
  name?: string;
  value: string;
  className?: string;
}

/** Compact key=value (or value-only) chip used in param previews. */
export const ParamChip = ({ name, value, className }: ParamChipProps): JSX.Element => (
  <WorkbenchTag
    meaning="metadata"
    className={cn(
      "max-w-40 gap-1 rounded-control border-border/70 bg-muted/30 px-2 py-1 font-normal",
      className,
    )}
    title={name ? `${name}=${value}` : value}
  >
    {name ? <span className="truncate text-muted-foreground">{name}</span> : null}
    <span className="truncate font-mono text-foreground">{value}</span>
  </WorkbenchTag>
);
