/**
 * MolPlot's one figure, as data: which series exist, which colour each file
 * takes, and how the series fall into panels for each Group by choice.
 *
 * - **Quantity** — a panel per series key; a colour per file, so the same
 *   quantity from two files sits in one panel in two colours.
 * - **Unit** — a panel per declared unit (`tags.unit`), its quantities
 *   overlaid in the file's colour and told apart by dash. A series with no
 *   declared unit keeps a panel of its own: molplot never guesses a unit.
 * - **File** — a panel per file; a colour per series. A file whose series do
 *   not share one unit is normalised, since raw values of different
 *   quantities on one axis say nothing.
 * - **None** — one panel; every series normalised to its own range, a colour
 *   per series.
 *
 * Pure: no React, no DOM.
 */

import type { SourceRead } from "./read-metrics";
import {
  buildScalarSeries,
  filterByTask,
  PALETTE,
  type ScalarPoint,
  unitsOf,
} from "./scalar-series";

export type GroupBy = "quantity" | "unit" | "file" | "none";

export const GROUP_BY_OPTIONS: readonly { value: GroupBy; label: string }[] = [
  { value: "quantity", label: "Quantity" },
  { value: "unit", label: "Unit" },
  { value: "file", label: "File" },
  { value: "none", label: "None" },
];

/** One series of one file. */
export interface FigureSeries {
  id: string;
  file: string;
  key: string;
  unit: string | null;
  points: readonly ScalarPoint[];
  latest: number;
  /** Every point has a measured wall clock. */
  timed: boolean;
  replayedFrom: readonly string[];
}

export interface PanelLine {
  id: string;
  /** Names the line in a tooltip and, when colours are per series, the legend. */
  label: string;
  color: string;
  /** Dash pattern index; 0 is solid. */
  dash: number;
  series: FigureSeries;
}

export interface PanelModel {
  id: string;
  title: string;
  /** The unit every line shares, if one does. */
  unit: string | null;
  note: string | null;
  normalised: boolean;
  lines: PanelLine[];
}

export interface LegendEntry {
  id: string;
  label: string;
  color: string;
}

const seriesId = (file: string, key: string): string => `${file}\u0000${key}`;

export const baseName = (path: string): string => path.slice(path.lastIndexOf("/") + 1) || path;

/** Every scalar series of every source, narrowed to one task (`null`: all). */
export const figureSeries = (sources: readonly SourceRead[], task: string | null): FigureSeries[] =>
  sources.flatMap((source) => {
    const records = filterByTask(source.records, task);
    const units = unitsOf(records);
    return buildScalarSeries(records).map((series) => ({
      id: seriesId(source.path, series.key),
      file: source.path,
      key: series.key,
      unit: units.get(series.key) ?? null,
      points: series.points,
      latest: series.latest,
      timed: series.timed ?? false,
      replayedFrom: series.replayedFrom ?? [],
    }));
  });

/** A palette colour per file, in list order: the checkbox and the legend share it. */
export const fileColors = (paths: readonly string[]): ReadonlyMap<string, string> =>
  new Map(paths.map((path, index) => [path, PALETTE[index % PALETTE.length]]));

/** File labels: the base name, or the attempt-relative path when two names collide. */
export const fileLabels = (paths: readonly string[]): ReadonlyMap<string, string> => {
  const counts = new Map<string, number>();
  for (const path of paths) counts.set(baseName(path), (counts.get(baseName(path)) ?? 0) + 1);
  return new Map(
    paths.map((path) => [path, (counts.get(baseName(path)) ?? 0) > 1 ? path : baseName(path)]),
  );
};

/** A key alone, or `key · file` when another file has the same key. */
const seriesLabels = (series: readonly FigureSeries[]): ReadonlyMap<string, string> => {
  const files = new Map<string, Set<string>>();
  for (const item of series) files.set(item.key, (files.get(item.key) ?? new Set()).add(item.file));
  return new Map(
    series.map((item) => [
      item.id,
      (files.get(item.key)?.size ?? 0) > 1 ? `${item.key} · ${baseName(item.file)}` : item.key,
    ]),
  );
};

/** Buckets in first-seen order. */
const bucket = <T>(items: readonly T[], keyOf: (item: T) => string): [string, T[]][] => {
  const buckets = new Map<string, T[]>();
  for (const item of items) {
    const key = keyOf(item);
    buckets.set(key, [...(buckets.get(key) ?? []), item]);
  }
  return [...buckets.entries()];
};

const sharedUnit = (series: readonly FigureSeries[]): string | null => {
  const unit = series[0]?.unit ?? null;
  return unit !== null && series.every((item) => item.unit === unit) ? unit : null;
};

const joinNotes = (...notes: (string | null)[]): string | null => {
  const kept = notes.filter((note): note is string => Boolean(note));
  return kept.length > 0 ? kept.join(" · ") : null;
};

const replayNote = (series: readonly FigureSeries[]): string | null => {
  const sources = [...new Set(series.flatMap((item) => item.replayedFrom))].sort();
  return sources.length > 0 ? `replayed from ${sources.join(", ")}` : null;
};

const distinctKeys = (series: readonly FigureSeries[]): string[] => [
  ...new Set(series.map((item) => item.key)),
];

interface Paint {
  labels: ReadonlyMap<string, string>;
  fileColor: (file: string) => string;
  seriesColor: (id: string) => string;
}

const byFile = (paint: Paint) => (series: FigureSeries, dash: number) => ({
  id: series.id,
  label: paint.labels.get(series.id) ?? series.key,
  color: paint.fileColor(series.file),
  dash,
  series,
});

const bySeries = (paint: Paint) => (series: FigureSeries) => ({
  id: series.id,
  label: paint.labels.get(series.id) ?? series.key,
  color: paint.seriesColor(series.id),
  dash: 0,
  series,
});

const quantityPanels = (series: readonly FigureSeries[], paint: Paint): PanelModel[] =>
  bucket(series, (item) => item.key).map(([key, items]) => ({
    id: `quantity:${key}`,
    title: key,
    unit: sharedUnit(items),
    note: replayNote(items),
    normalised: false,
    lines: items.map((item) => byFile(paint)(item, 0)),
  }));

const unitPanels = (series: readonly FigureSeries[], paint: Paint): PanelModel[] =>
  bucket(series, (item) => (item.unit === null ? `key:${item.key}` : `unit:${item.unit}`)).map(
    ([id, items]) => {
      const keys = distinctKeys(items);
      const unit = items[0]?.unit ?? null;
      return {
        id: `unit:${id}`,
        title: unit ?? items[0]?.key ?? id,
        unit: null,
        note: joinNotes(unit === null ? null : keys.join(" · "), replayNote(items)),
        normalised: false,
        lines: items.map((item) => byFile(paint)(item, keys.indexOf(item.key))),
      };
    },
  );

const filePanels = (
  series: readonly FigureSeries[],
  paint: Paint,
  labels: ReadonlyMap<string, string>,
): PanelModel[] =>
  bucket(series, (item) => item.file).map(([file, items]) => {
    const unit = sharedUnit(items);
    const normalised = distinctKeys(items).length > 1 && unit === null;
    return {
      id: `file:${file}`,
      title: labels.get(file) ?? baseName(file),
      unit,
      note: joinNotes(normalised ? "normalised" : null, replayNote(items)),
      normalised,
      lines: items.map(bySeries(paint)),
    };
  });

const nonePanel = (series: readonly FigureSeries[], paint: Paint): PanelModel[] =>
  series.length === 0
    ? []
    : [
        {
          id: "none",
          title: "All series",
          unit: null,
          note: joinNotes("normalised", replayNote(series)),
          normalised: true,
          lines: series.map(bySeries(paint)),
        },
      ];

/** The series of the checked files, as panels for one Group by choice. */
export const groupPanels = (
  series: readonly FigureSeries[],
  groupBy: GroupBy,
  colors: ReadonlyMap<string, string>,
  labels: ReadonlyMap<string, string> = fileLabels([...new Set(series.map((s) => s.file))]),
): PanelModel[] => {
  const order = new Map(series.map((item, index) => [item.id, index]));
  const paint: Paint = {
    labels: seriesLabels(series),
    fileColor: (file) => colors.get(file) ?? PALETTE[0],
    seriesColor: (id) => PALETTE[(order.get(id) ?? 0) % PALETTE.length],
  };
  if (groupBy === "unit") return unitPanels(series, paint);
  if (groupBy === "file") return filePanels(series, paint, labels);
  if (groupBy === "none") return nonePanel(series, paint);
  return quantityPanels(series, paint);
};

/** Colours are per file for Quantity and Unit, per series for File and None. */
export const coloursBySeries = (groupBy: GroupBy): boolean =>
  groupBy === "file" || groupBy === "none";

/** The figure's legend: the files drawn, or every series line. */
export const legendOf = (
  groupBy: GroupBy,
  panels: readonly PanelModel[],
  files: readonly LegendEntry[],
): LegendEntry[] => {
  if (!coloursBySeries(groupBy)) return [...files];
  const seen = new Map<string, LegendEntry>();
  for (const line of panels.flatMap((panel) => panel.lines)) {
    if (!seen.has(line.id))
      seen.set(line.id, { id: line.id, label: line.label, color: line.color });
  }
  return [...seen.values()];
};
