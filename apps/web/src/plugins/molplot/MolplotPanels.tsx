/**
 * The panels of MolPlot's figure: a series panel (one Vega-Lite chart of a
 * panel's lines) and a run's own figure (`*.mlp.vl.json`), each in the SDK's
 * `RunView.Panel` (name, unit, last value, enlarge), drawn through the app's
 * one Vega wrapper (`OverviewChart`) in the app's type and palette.
 */

import { RunView, useAttemptText } from "@molcrafts/molab-plugin/ui";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@molcrafts/ui";
import { type JSX, type ReactNode, useMemo, useState } from "react";
import { OverviewChart } from "@/app/components/entity/gauges/vega/OverviewChart";
import { molplotDisplayName } from "./display-name";
import type { LegendEntry, PanelModel } from "./figure-model";
import {
  axisLabelExpr,
  logAxis,
  type MolplotStyle,
  panelNote,
  panelRows,
  panelValue,
  showsRaw,
} from "./panel-data";
import {
  figureSpec,
  figureTitle,
  PANEL_HEIGHT,
  PANEL_HEIGHT_WIDE,
  parseFigure,
  seriesSpec,
} from "./panel-spec";

const NO_DATA = {};

/** A panel's chart again, larger, in a dialog. */
const Enlarged = ({
  title,
  open,
  onOpenChange,
  children,
}: {
  title: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: ReactNode;
}): JSX.Element => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="flex w-[min(90vw,64rem)] max-w-none flex-col gap-3 p-4 sm:max-w-none">
      <DialogHeader className="pr-8">
        <DialogTitle className="truncate text-body-lg">{title}</DialogTitle>
      </DialogHeader>
      {open ? children : null}
    </DialogContent>
  </Dialog>
);

const SeriesChart = ({
  panel,
  style,
  height,
}: {
  panel: PanelModel;
  style: MolplotStyle;
  height: number;
}): JSX.Element => {
  const rows = useMemo(() => panelRows(panel, style), [panel, style]);
  const data = useMemo(() => ({ rows }), [rows]);
  const options = {
    height,
    time: style.x === "time",
    log: logAxis(style, panel),
    yLabels: axisLabelExpr(style),
    raw: showsRaw(style),
  };
  return (
    <OverviewChart
      label={`${panel.title}${panel.unit ? ` (${panel.unit})` : ""}`}
      spec={(palette) => seriesSpec(palette, options)}
      specKey={JSON.stringify(options)}
      data={data}
      height={height}
    />
  );
};

export const SeriesPanel = ({
  panel,
  style,
  wide,
}: {
  panel: PanelModel;
  style: MolplotStyle;
  /** Alone in the figure: full width and taller. */
  wide: boolean;
}): JSX.Element => {
  const [enlarged, setEnlarged] = useState(false);
  return (
    <RunView.Panel
      title={panel.title}
      unit={panel.unit ?? undefined}
      note={panelNote(style, panel)}
      value={panelValue(panel, style)}
      onEnlarge={() => setEnlarged(true)}
    >
      <SeriesChart panel={panel} style={style} height={wide ? PANEL_HEIGHT_WIDE : PANEL_HEIGHT} />
      <Enlarged title={panel.title} open={enlarged} onOpenChange={setEnlarged}>
        <SeriesChart panel={panel} style={style} height={PANEL_HEIGHT_WIDE + PANEL_HEIGHT} />
      </Enlarged>
    </RunView.Panel>
  );
};

const FigureChart = ({
  label,
  authored,
  color,
  height,
}: {
  label: string;
  authored: Record<string, unknown>;
  color: string;
  height: number;
}): JSX.Element => (
  <OverviewChart
    label={label}
    spec={(palette) => figureSpec(palette, authored, color, height)}
    specKey={`${label}:${color}:${height}`}
    data={NO_DATA}
    height={height}
  />
);

const readFigure = (
  text: string | undefined,
): { authored: Record<string, unknown> | null; error: string | null } => {
  if (text === undefined) return { authored: null, error: null };
  try {
    return { authored: parseFigure(text), error: null };
  } catch (error) {
    return { authored: null, error: error instanceof Error ? error.message : String(error) };
  }
};

/** A run's own Vega-Lite figure, as a panel in its file's colour. */
export const FigurePanel = ({
  path,
  color,
  wide,
}: {
  path: string;
  color: string;
  wide: boolean;
}): JSX.Element => {
  const [enlarged, setEnlarged] = useState(false);
  const read = useAttemptText(path);
  const { authored, error } = useMemo(() => readFigure(read.data), [read.data]);
  const title = (authored && figureTitle(authored)) ?? molplotDisplayName(path);
  const height = wide ? PANEL_HEIGHT_WIDE : PANEL_HEIGHT;
  const failure = read.error ?? error;
  return (
    <RunView.Panel title={title} note="figure" onEnlarge={() => setEnlarged(true)}>
      {authored ? (
        <FigureChart label={title} authored={authored} color={color} height={height} />
      ) : (
        <p className="py-6 text-center text-label text-muted-foreground">
          {failure ?? "Reading the figure…"}
        </p>
      )}
      {authored ? (
        <Enlarged title={title} open={enlarged} onOpenChange={setEnlarged}>
          <FigureChart
            label={title}
            authored={authored}
            color={color}
            height={PANEL_HEIGHT_WIDE + PANEL_HEIGHT}
          />
        </Enlarged>
      ) : null}
    </RunView.Panel>
  );
};

/** The figure's legend (RunView `header`): a dot in each colour and its name. */
export const Legend = ({ entries }: { entries: readonly LegendEntry[] }): JSX.Element => (
  <ul aria-label="Legend" className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
    {entries.map((entry) => (
      <li key={entry.id} className="flex min-w-0 items-center gap-1 text-label">
        <span
          aria-hidden
          className="size-2 flex-none rounded-full"
          style={{ background: entry.color }}
        />
        <span className="truncate">{entry.label}</span>
      </li>
    ))}
  </ul>
);
