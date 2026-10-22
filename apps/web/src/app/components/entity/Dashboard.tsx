import { WorkbenchAction, WorkbenchIconAction, WorkbenchTag } from "@/components/workbench";
// ─────────────────────────────────────────────────────────────────────────────
// Dashboard primitives — section / chart vocabulary for entity Overviews.
// Shared by Project / Experiment / Run so hierarchy pages share one surface
// language (canvas shell + mono section headers + hairline borders). Pure
// presentation only; no shadcn Card layout wrappers.
// ─────────────────────────────────────────────────────────────────────────────

import { Check, Copy, type LucideIcon } from "lucide-react";
import {
  Children,
  type JSX,
  type ReactNode,
  type PointerEvent as ReactPointerEvent,
  useId,
  useState,
} from "react";

import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import { cn } from "@/lib/utils";

import { StatusBarChart } from "./InstrumentChart";

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
    <dt className="text-label text-muted-foreground">{label}</dt>
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
  <div className={cn("mx-auto w-full max-w-none space-y-4 px-4 py-3", className)}>{children}</div>
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
        ? "flex h-full min-h-0 w-full flex-col px-3 pt-2"
        : "mx-auto w-full max-w-none space-y-4 px-4 py-3",
      className,
    )}
  >
    {children}
  </div>
);

/** Instrument row on an Overview. Empty slots are dropped, so a quiet scope does not draw a hollow gauge. */
export const OverviewInstruments = ({ children }: { children: ReactNode }): JSX.Element | null => {
  const items = Children.toArray(children);
  if (items.length === 0) return null;
  return (
    <div className="grid items-start gap-x-4 gap-y-4 md:grid-cols-2 xl:grid-cols-3">{items}</div>
  );
};

/** The inventory that follows the instruments. */
export const OverviewList = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): JSX.Element => (
  <section className="min-w-0">
    <h3 className="mb-2 text-label font-medium text-foreground">{title}</h3>
    {children}
  </section>
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
  /** Drag the header. Buttons in the action slot do not start a drag. */
  onHeaderPointerDown?: (event: ReactPointerEvent<HTMLElement>) => void;
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
  onHeaderPointerDown,
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
        <header
          className={cn(
            "flex h-control-compact items-center gap-2 px-3",
            onHeaderPointerDown && "cursor-grab touch-none active:cursor-grabbing",
          )}
          onPointerDown={onHeaderPointerDown}
        >
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
              title={typeof title === "string" ? title : undefined}
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
            <span
              title={typeof description === "string" ? description : undefined}
              className="hidden min-w-0 truncate text-label text-muted-foreground sm:inline"
            >
              {description}
            </span>
          )}
          <div
            className="ml-auto flex shrink-0 items-center gap-1"
            onPointerDown={(event) => event.stopPropagation()}
          >
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
  /** Draw the status bars. Default true. Ignored by meter and bar. */
  legend?: boolean;
  /** Noun for the accessible total. Default "runs". */
  unit?: string;
  /** Statuses drawn on the face. Default is every group. */
  groups?: readonly StatusGroupId[];
  /**
   * bars: one horizontal bar per status.
   * meter: a thin stacked track, for a row of mixes.
   * bar: the same track, for a table cell.
   * Default is bars, or bar when `legend` is false.
   */
  variant?: "bars" | "meter" | "bar";
  className?: string;
  /** Pixel height of the bar chart. Ignored by meter and bar. */
  height?: number;
}

/**
 * Status as a chart. The overview is one horizontal bar per status.
 * `variant="bar"` and `variant="meter"` (also `legend={false}`) stay a thin
 * stacked track for a table cell or a row of small multiples.
 */
export const StatusDistribution = ({
  counts,
  legend = true,
  unit = "runs",
  groups,
  variant,
  className,
  height,
}: StatusDistributionProps): JSX.Element => {
  const specs = groups ? STATUS_GROUPS.filter((group) => groups.includes(group.id)) : STATUS_GROUPS;
  const total = groups ? specs.reduce((sum, group) => sum + counts[group.id], 0) : counts.total;
  const empty = total === 0;
  const occupied = specs.filter((group) => counts[group.id] > 0);
  const label = empty ? `No ${unit}` : `Status mix across ${total} ${unit}`;
  const face = variant ?? (legend ? "bars" : "bar");

  if (face === "bar" || face === "meter") {
    return (
      <div
        className={cn("flex h-1.5 w-full overflow-hidden rounded-control bg-muted", className)}
        role="img"
        aria-label={label}
      >
        {!empty &&
          occupied.map((group) => (
            <div
              key={group.id}
              title={`${group.label}: ${counts[group.id]}`}
              className="h-full min-w-hairline"
              style={{
                width: `${(counts[group.id] / total) * 100}%`,
                backgroundColor: group.color,
              }}
            />
          ))}
      </div>
    );
  }

  return <StatusBarChart counts={counts} groups={groups} label={label} height={height} />;
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
