import { describe, expect, it } from "@rstest/core";

import {
  addWidget,
  compactWidgets,
  type DashboardWidget,
  defaultWidgets,
  moveWidget,
  parseLayout,
  removeWidget,
  resizeWidget,
  serializeLayout,
} from "@/app/dashboard/layout";

const overlaps = (left: DashboardWidget, right: DashboardWidget): boolean =>
  left.id !== right.id &&
  left.x < right.x + right.w &&
  left.x + left.w > right.x &&
  left.y < right.y + right.h &&
  left.y + left.h > right.y;

const activity = (id: string, x: number, y: number, w = 4, h = 2): DashboardWidget => ({
  id,
  kind: "activity",
  x,
  y,
  w,
  h,
  options: { window: "24h", events: "both" },
});

describe("dashboard layout", () => {
  it("starts from the six workspace panels", () => {
    const widgets = defaultWidgets();
    expect(widgets.map((widget) => widget.kind)).toEqual([
      "execution-status",
      "activity",
      "backends",
      "run-duration",
      "schedule",
      "needs-attention",
    ]);
    expect(widgets.some((left) => widgets.some((right) => overlaps(left, right)))).toBe(false);
  });

  it("rejects a missing, broken, or foreign layout", () => {
    expect(parseLayout(null).map((widget) => widget.id)).toEqual(
      defaultWidgets().map((widget) => widget.id),
    );
    expect(parseLayout("not json").map((widget) => widget.id)).toEqual(
      defaultWidgets().map((widget) => widget.id),
    );
    expect(
      parseLayout(JSON.stringify({ version: 2, widgets: [] })).map((widget) => widget.id),
    ).toEqual(defaultWidgets().map((widget) => widget.id));
  });

  it("keeps a valid widget and repairs its options", () => {
    const raw = JSON.stringify({
      version: 1,
      widgets: [
        {
          id: "backends",
          kind: "backends",
          x: 0,
          y: 2,
          w: 1,
          h: 1,
          options: { limit: 99 },
        },
        { id: "nope", kind: "kpi", x: 0, y: 0, w: 2, h: 2, options: {} },
        {
          id: "attention",
          kind: "needs-attention",
          x: 0,
          y: 0,
          w: 4,
          h: 3,
          options: { statuses: ["running"], limit: 3 },
        },
      ],
    });
    const widgets = parseLayout(raw);
    const backends = widgets.find((widget) => widget.id === "backends");
    const attention = widgets.find((widget) => widget.id === "attention");
    expect(widgets.map((widget) => widget.id).sort()).toEqual(["attention", "backends"]);
    expect(backends).toMatchObject({ w: 4, h: 3, options: { limit: 6 } });
    expect(attention?.kind === "needs-attention" && attention.options.statuses).toEqual(["failed"]);
    expect(attention?.kind === "needs-attention" && attention.options.limit).toBe(3);
  });

  it("closes a vertical gap without overlapping", () => {
    const compacted = compactWidgets([activity("a", 0, 0), activity("b", 0, 5)]);
    expect(compacted.find((widget) => widget.id === "b")?.y).toBe(2);
  });

  it("moves an overlapping widget to the nearest free cell", () => {
    const moved = moveWidget([activity("a", 0, 0), activity("b", 4, 0)], "b", 0, 0);
    const settled = moved.find((widget) => widget.id === "b");
    expect(settled).toMatchObject({ x: 0, y: 2 });
    expect(moved.some((left) => moved.some((right) => overlaps(left, right)))).toBe(false);
  });

  it("refuses a resize below the widget minimum", () => {
    const resized = resizeWidget([activity("a", 0, 0)], "a", 1, 1);
    expect(resized[0]).toMatchObject({ w: 4, h: 2 });
  });

  it("appends a new widget under the grid and drops it on remove", () => {
    const start = [activity("a", 0, 0, 6, 3)];
    const added = addWidget(start, "schedule", "extra");
    expect(added.find((widget) => widget.id === "extra")).toMatchObject({
      x: 0,
      y: 3,
      kind: "schedule",
    });
    expect(removeWidget(added, "a").map((widget) => widget.id)).toEqual(["extra"]);
    expect(removeWidget(added, "a")[0]?.y).toBe(0);
  });

  it("round-trips through storage json", () => {
    const widgets = defaultWidgets();
    const restored = parseLayout(serializeLayout(widgets));
    const byId = (items: DashboardWidget[]) =>
      [...items].sort((left, right) => left.id.localeCompare(right.id));
    expect(byId(restored)).toEqual(byId(widgets));
  });
});
