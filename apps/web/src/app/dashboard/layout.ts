import type { StatusGroupId } from "@/app/runs/statusGroups";

/** Operator chrome for the workspace dashboard. Not a workspace fact. */
export const DASHBOARD_LAYOUT_KEY = "molab.dashboard.layout.v1";

export const DASHBOARD_COLUMNS = 12;

export const DASHBOARD_ROW_PX = 72;

/** Space between cells. A span includes the gaps between its rows. */
export const DASHBOARD_GAP_PX = 16;

const LAYOUT_VERSION = 1;

const MAX_HEIGHT = 16;

export const STATUS_CHOICES = [
  "running",
  "pending",
  "succeeded",
  "failed",
  "cancelled",
] as const satisfies readonly StatusGroupId[];

export type DashboardWidgetKind =
  | "execution-status"
  | "activity"
  | "backends"
  | "run-duration"
  | "schedule"
  | "needs-attention";

/**
 * Each widget draws the one gauge its data has a shape for — a ledger for a
 * status mix, mirrored columns for events in time — so none offers a choice
 * of chart mark. A stored `mark` from an older layout is dropped on read.
 */
export interface ExecutionStatusOptions {
  statuses: StatusGroupId[];
}

export interface ActivityOptions {
  window: "24h" | "7d";
  events: "starts" | "finishes" | "both";
}

export interface BackendsOptions {
  limit: 3 | 6 | 12;
}

export interface RunDurationOptions {
  scope: "finished" | "succeeded";
}

export interface ScheduleOptions {
  limit: 4 | 8 | 16;
}

export interface NeedsAttentionOptions {
  statuses: Array<"failed" | "cancelled">;
  limit: 3 | 6 | 12;
}

export type DashboardWidget =
  | Widget<"execution-status", ExecutionStatusOptions>
  | Widget<"activity", ActivityOptions>
  | Widget<"backends", BackendsOptions>
  | Widget<"run-duration", RunDurationOptions>
  | Widget<"schedule", ScheduleOptions>
  | Widget<"needs-attention", NeedsAttentionOptions>;

interface Widget<Kind extends DashboardWidgetKind, Options> {
  id: string;
  kind: Kind;
  x: number;
  y: number;
  w: number;
  h: number;
  options: Options;
}

interface WidgetSpec {
  kind: DashboardWidgetKind;
  title: string;
  description: string;
  defaultW: number;
  defaultH: number;
  minW: number;
  minH: number;
}

export const WIDGET_CATALOG: readonly WidgetSpec[] = [
  {
    kind: "execution-status",
    title: "Execution status",
    description: "Attempts by status",
    defaultW: 12,
    defaultH: 2,
    minW: 6,
    minH: 2,
  },
  {
    kind: "activity",
    title: "Activity",
    description: "Starts and finishes",
    defaultW: 12,
    defaultH: 3,
    minW: 4,
    minH: 2,
  },
  {
    kind: "backends",
    title: "Backends",
    description: "Status mix per backend",
    defaultW: 6,
    defaultH: 3,
    minW: 4,
    minH: 3,
  },
  {
    kind: "run-duration",
    title: "Run duration",
    description: "Wall-clock spread",
    defaultW: 6,
    defaultH: 3,
    minW: 4,
    minH: 3,
  },
  {
    kind: "schedule",
    title: "Schedule",
    description: "Recently active runs",
    defaultW: 12,
    defaultH: 5,
    minW: 5,
    minH: 3,
  },
  {
    kind: "needs-attention",
    title: "Needs attention",
    description: "Failed and cancelled runs",
    defaultW: 5,
    defaultH: 3,
    minW: 3,
    minH: 3,
  },
];

const specFor = (kind: DashboardWidgetKind): WidgetSpec => {
  const spec = WIDGET_CATALOG.find((item) => item.kind === kind);
  if (!spec) throw new Error(`unknown widget ${kind}`);
  return spec;
};

export const widgetTitle = (kind: DashboardWidgetKind): string => specFor(kind).title;

export const widgetDescription = (kind: DashboardWidgetKind): string => specFor(kind).description;

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const oneOf = <T extends string | number>(value: unknown, allowed: readonly T[], fallback: T): T =>
  (allowed as readonly unknown[]).includes(value) ? (value as T) : fallback;

const statusList = (value: unknown, fallback: StatusGroupId[]): StatusGroupId[] => {
  if (!Array.isArray(value)) return fallback;
  const picked = value.filter(
    (item): item is StatusGroupId =>
      typeof item === "string" && (STATUS_CHOICES as readonly string[]).includes(item),
  );
  return picked.length > 0 ? [...new Set(picked)] : fallback;
};

export const defaultOptions = (kind: DashboardWidgetKind): DashboardWidget["options"] => {
  switch (kind) {
    case "execution-status":
      return { statuses: [...STATUS_CHOICES] };
    case "activity":
      return { window: "24h", events: "both" };
    case "backends":
      return { limit: 6 };
    case "run-duration":
      return { scope: "finished" };
    case "schedule":
      return { limit: 8 };
    case "needs-attention":
      return { statuses: ["failed"], limit: 6 };
  }
};

const repairOptions = (kind: DashboardWidgetKind, value: unknown): DashboardWidget["options"] => {
  const raw = isRecord(value) ? value : {};
  switch (kind) {
    case "execution-status":
      return { statuses: statusList(raw.statuses, [...STATUS_CHOICES]) };
    case "activity":
      return {
        window: oneOf(raw.window, ["24h", "7d"] as const, "24h"),
        events: oneOf(raw.events, ["starts", "finishes", "both"] as const, "both"),
      };
    case "backends":
      return { limit: oneOf(raw.limit, [3, 6, 12] as const, 6) };
    case "run-duration":
      return { scope: oneOf(raw.scope, ["finished", "succeeded"] as const, "finished") };
    case "schedule":
      return { limit: oneOf(raw.limit, [4, 8, 16] as const, 8) };
    case "needs-attention": {
      const statuses = statusList(raw.statuses, ["failed"]).filter(
        (status): status is "failed" | "cancelled" => status === "failed" || status === "cancelled",
      );
      return {
        statuses: statuses.length > 0 ? statuses : ["failed"],
        limit: oneOf(raw.limit, [3, 6, 12] as const, 6),
      };
    }
  }
};

const finite = (value: unknown, fallback: number): number =>
  typeof value === "number" && Number.isFinite(value) ? Math.round(value) : fallback;

const place = (
  kind: DashboardWidgetKind,
  id: string,
  x: number,
  y: number,
  w: number,
  h: number,
  options: unknown,
): DashboardWidget => {
  const spec = specFor(kind);
  const width = clamp(w, spec.minW, DASHBOARD_COLUMNS);
  const height = clamp(h, spec.minH, MAX_HEIGHT);
  const widget = {
    id,
    kind,
    x: clamp(x, 0, DASHBOARD_COLUMNS - width),
    y: Math.max(0, y),
    w: width,
    h: height,
    options: repairOptions(kind, options),
  };
  return widget as DashboardWidget;
};

/**
 * The composed default. The status ledger sits in the page lead, not here.
 * Column edges stagger row to row (8|4, then 7|5) so the sheet does not read
 * as one ruled grid of matching tiles.
 */
export const defaultWidgets = (): DashboardWidget[] => [
  place("activity", "activity", 0, 0, 8, 3, defaultOptions("activity")),
  place("needs-attention", "needs-attention", 8, 0, 4, 3, defaultOptions("needs-attention")),
  place("run-duration", "run-duration", 0, 3, 7, 3, defaultOptions("run-duration")),
  place("backends", "backends", 7, 3, 5, 3, defaultOptions("backends")),
  place("schedule", "schedule", 0, 6, 12, 5, defaultOptions("schedule")),
];

type Footprint = { kind: DashboardWidgetKind; x: number; y: number; w: number; h: number };

/**
 * Mosaics this page shipped as its default before. An operator who never
 * moved a widget still has one of these in local storage; reading it back
 * adopts the current default instead of freezing the old one.
 */
const LEGACY_DEFAULTS: readonly (readonly Footprint[])[] = [
  [
    { kind: "execution-status", x: 0, y: 0, w: 6, h: 4 },
    { kind: "activity", x: 6, y: 0, w: 6, h: 3 },
    { kind: "backends", x: 0, y: 4, w: 6, h: 4 },
    { kind: "run-duration", x: 6, y: 3, w: 6, h: 5 },
    { kind: "schedule", x: 0, y: 8, w: 8, h: 5 },
    { kind: "needs-attention", x: 8, y: 8, w: 4, h: 5 },
  ],
  [
    { kind: "execution-status", x: 0, y: 0, w: 7, h: 3 },
    { kind: "needs-attention", x: 7, y: 0, w: 5, h: 3 },
    { kind: "activity", x: 0, y: 3, w: 12, h: 3 },
    { kind: "backends", x: 0, y: 6, w: 6, h: 3 },
    { kind: "run-duration", x: 6, y: 6, w: 6, h: 3 },
    { kind: "schedule", x: 0, y: 9, w: 12, h: 5 },
  ],
];

/** Same footprint, ids still the kind names: nobody arranged this layout. */
const isUntouchedLegacyLayout = (widgets: readonly DashboardWidget[]): boolean =>
  LEGACY_DEFAULTS.some(
    (legacy) =>
      widgets.length === legacy.length &&
      legacy.every((expected) =>
        widgets.some(
          (widget) =>
            widget.kind === expected.kind &&
            widget.id === expected.kind &&
            widget.x === expected.x &&
            widget.y === expected.y &&
            widget.w === expected.w &&
            widget.h === expected.h,
        ),
      ),
  );

const isKind = (value: unknown): value is DashboardWidgetKind =>
  WIDGET_CATALOG.some((item) => item.kind === value);

const parseWidget = (value: unknown): DashboardWidget | null => {
  if (!isRecord(value) || !isKind(value.kind) || typeof value.id !== "string" || value.id === "") {
    return null;
  }
  const spec = specFor(value.kind);
  return place(
    value.kind,
    value.id,
    finite(value.x, 0),
    finite(value.y, 0),
    finite(value.w, spec.defaultW),
    finite(value.h, spec.defaultH),
    value.options,
  );
};

export const parseLayout = (raw: string | null): DashboardWidget[] => {
  if (!raw) return defaultWidgets();
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || parsed.version !== LAYOUT_VERSION || !Array.isArray(parsed.widgets)) {
      return defaultWidgets();
    }
    const widgets = parsed.widgets
      .map(parseWidget)
      .filter((widget): widget is DashboardWidget => widget !== null);
    const ids = new Set<string>();
    const unique = widgets.filter((widget) => {
      if (ids.has(widget.id)) return false;
      ids.add(widget.id);
      return true;
    });
    if (unique.length === 0 || isUntouchedLegacyLayout(unique)) return defaultWidgets();
    return compactWidgets(unique);
  } catch {
    return defaultWidgets();
  }
};

export const serializeLayout = (widgets: DashboardWidget[]): string =>
  JSON.stringify({ version: LAYOUT_VERSION, widgets });

interface Rect {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

const overlaps = (left: Rect, right: Rect): boolean =>
  left.x < right.x + right.w &&
  left.x + left.w > right.x &&
  left.y < right.y + right.h &&
  left.y + left.h > right.y;

const overlapsAny = (widgets: readonly Rect[], rect: Rect): boolean =>
  widgets.some((widget) => overlaps(widget, rect));

const nearestSlot = (
  others: readonly DashboardWidget[],
  wanted: DashboardWidget,
): DashboardWidget => {
  if (!overlapsAny(others, wanted)) return wanted;
  const floor = others.reduce((max, widget) => Math.max(max, widget.y + widget.h), 0);
  let best: DashboardWidget | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let y = 0; y <= floor; y += 1) {
    for (let x = 0; x <= DASHBOARD_COLUMNS - wanted.w; x += 1) {
      const candidate = { ...wanted, x, y };
      if (overlapsAny(others, candidate)) continue;
      const distance = Math.abs(x - wanted.x) + Math.abs(y - wanted.y);
      if (distance < bestDistance) {
        best = candidate;
        bestDistance = distance;
      }
    }
  }
  return best ?? { ...wanted, x: 0, y: floor };
};

/** Pull every widget up until it touches another widget or the top. */
export const compactWidgets = (widgets: readonly DashboardWidget[]): DashboardWidget[] => {
  const sorted = [...widgets].sort(
    (left, right) => left.y - right.y || left.x - right.x || left.id.localeCompare(right.id),
  );
  const placed: DashboardWidget[] = [];
  for (const widget of sorted) {
    const freed = nearestSlot(placed, widget);
    let y = freed.y;
    while (y > 0 && !overlapsAny(placed, { ...freed, y: y - 1 })) y -= 1;
    placed.push({ ...freed, y });
  }
  return placed;
};

export const moveWidget = (
  widgets: readonly DashboardWidget[],
  id: string,
  x: number,
  y: number,
): DashboardWidget[] => {
  const current = widgets.find((widget) => widget.id === id);
  if (!current) return [...widgets];
  const width = current.w;
  const draft = {
    ...current,
    x: clamp(Math.round(x), 0, DASHBOARD_COLUMNS - width),
    y: Math.max(0, Math.round(y)),
  };
  const others = widgets.filter((widget) => widget.id !== id);
  return compactWidgets([...others, nearestSlot(others, draft)]);
};

export const resizeWidget = (
  widgets: readonly DashboardWidget[],
  id: string,
  w: number,
  h: number,
): DashboardWidget[] => {
  const current = widgets.find((widget) => widget.id === id);
  if (!current) return [...widgets];
  const spec = specFor(current.kind);
  const width = clamp(Math.round(w), spec.minW, DASHBOARD_COLUMNS);
  const draft = place(
    current.kind,
    current.id,
    current.x,
    current.y,
    width,
    Math.round(h),
    current.options,
  );
  const others = widgets.filter((widget) => widget.id !== id);
  return compactWidgets([...others, nearestSlot(others, draft)]);
};

export const addWidget = (
  widgets: readonly DashboardWidget[],
  kind: DashboardWidgetKind,
  id: string,
): DashboardWidget[] => {
  if (widgets.some((widget) => widget.kind === kind)) return [...widgets];
  const spec = specFor(kind);
  const y = widgets.reduce((max, widget) => Math.max(max, widget.y + widget.h), 0);
  return [...widgets, place(kind, id, 0, y, spec.defaultW, spec.defaultH, defaultOptions(kind))];
};

export const removeWidget = (widgets: readonly DashboardWidget[], id: string): DashboardWidget[] =>
  compactWidgets(widgets.filter((widget) => widget.id !== id));

export const readingOrder = (widgets: readonly DashboardWidget[]): DashboardWidget[] =>
  [...widgets].sort(
    (left, right) => left.y - right.y || left.x - right.x || left.id.localeCompare(right.id),
  );

let widgetCounter = 0;

export const widgetId = (): string => {
  widgetCounter += 1;
  return `w${widgetCounter.toString(36)}${Math.random().toString(36).slice(2, 8)}`;
};
