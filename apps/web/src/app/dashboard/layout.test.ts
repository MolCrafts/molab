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
  it("starts from five panels; the status ledger leads the page instead", () => {
    const widgets = defaultWidgets();
    expect(widgets.map((widget) => widget.kind)).toEqual([
      "activity",
      "needs-attention",
      "run-duration",
      "backends",
      "schedule",
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

  it("keeps edited options and drops a chart mark an older layout stored", () => {
    const kept = parseLayout(
      JSON.stringify({
        version: 1,
        widgets: [
          {
            id: "execution-status",
            kind: "execution-status",
            x: 0,
            y: 0,
            w: 12,
            h: 2,
            options: { statuses: ["failed"], mark: "bar" },
          },
          {
            id: "activity",
            kind: "activity",
            x: 0,
            y: 3,
            w: 12,
            h: 3,
            options: { window: "7d", events: "starts", mark: "plot" },
          },
        ],
      }),
    );
    const status = kept.find((widget) => widget.id === "execution-status");
    const activityWidget = kept.find((widget) => widget.id === "activity");
    expect(status?.options).toEqual({ statuses: ["failed"] });
    expect(activityWidget?.options).toEqual({ window: "7d", events: "starts" });
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

  it("refuses a second widget of the same kind", () => {
    const start = [activity("a", 0, 0, 6, 3)];
    const added = addWidget(start, "schedule", "extra");
    const again = addWidget(added, "schedule", "again");
    expect(again.map((widget) => widget.id)).toEqual(["a", "extra"]);
  });

  it("adopts the composed default over the previous shipped default", () => {
    const previous = {
      version: 1,
      widgets: [
        ["execution-status", 0, 0, 7, 3],
        ["needs-attention", 7, 0, 5, 3],
        ["activity", 0, 3, 12, 3],
        ["backends", 0, 6, 6, 3],
        ["run-duration", 6, 6, 6, 3],
        ["schedule", 0, 9, 12, 5],
      ].map(([kind, x, y, w, h]) => ({ id: kind, kind, x, y, w, h, options: {} })),
    };
    const widgets = parseLayout(JSON.stringify(previous));
    expect(widgets.map((widget) => [widget.kind, widget.x, widget.y, widget.w, widget.h])).toEqual(
      defaultWidgets().map((widget) => [widget.kind, widget.x, widget.y, widget.w, widget.h]),
    );
  });

  it("adopts the composed default when storage still has the untouched mosaic", () => {
    const legacy = {
      version: 1,
      widgets: [
        { id: "execution-status", kind: "execution-status", x: 0, y: 0, w: 6, h: 4, options: {} },
        {
          id: "activity",
          kind: "activity",
          x: 6,
          y: 0,
          w: 6,
          h: 3,
          options: { window: "24h", events: "both" },
        },
        { id: "backends", kind: "backends", x: 0, y: 4, w: 6, h: 4, options: { limit: 6 } },
        {
          id: "run-duration",
          kind: "run-duration",
          x: 6,
          y: 3,
          w: 6,
          h: 5,
          options: { scope: "finished" },
        },
        { id: "schedule", kind: "schedule", x: 0, y: 8, w: 8, h: 5, options: { limit: 8 } },
        {
          id: "needs-attention",
          kind: "needs-attention",
          x: 8,
          y: 8,
          w: 4,
          h: 5,
          options: { statuses: ["failed"], limit: 6 },
        },
      ],
    };
    const widgets = parseLayout(JSON.stringify(legacy));
    expect(widgets.map((widget) => [widget.kind, widget.x, widget.y, widget.w, widget.h])).toEqual(
      defaultWidgets().map((widget) => [widget.kind, widget.x, widget.y, widget.w, widget.h]),
    );
  });

  it("round-trips through storage json", () => {
    const widgets = defaultWidgets();
    const restored = parseLayout(serializeLayout(widgets));
    const byId = (items: DashboardWidget[]) =>
      [...items].sort((left, right) => left.id.localeCompare(right.id));
    expect(byId(restored)).toEqual(byId(widgets));
  });
});
