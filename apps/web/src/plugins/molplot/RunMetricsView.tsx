import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Slider,
  Switch,
} from "@molcrafts/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, Maximize2 } from "lucide-react";
import { useMemo, useState } from "react";
import { DashboardCanvas, EmptyState, OverviewSection } from "@/app/components/entity";
import { journalRefetchInterval, runKeys } from "@/app/state/entityQueries";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";
import { CHART_SERIES_PALETTE } from "@/lib/chart-tokens";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";
import { cn } from "@/lib/utils";
import {
  ChartLegend,
  type ChartLegendPlacement,
  ChartWorkbench,
  MolplotLineChart,
} from "@/plugins/molplot";
import {
  HistogramCard,
  ImageCard,
  JsonCard,
  ReplayMarker,
  TaskFilter,
  TextCard,
} from "@/plugins/molplot/MetricCards";
import {
  buildMetricCards,
  filterByTask,
  listTasks,
  replayedFromOf,
} from "@/plugins/molplot/metric-cards";
import { readExecutionMetrics } from "@/plugins/molplot/read-metrics";
import { STEP_INTERVAL } from "@/plugins/molplot/resolution";
import {
  DEFAULT_SCALAR_FORMAT,
  formatScalar,
  type ScalarFormat,
  type ScalarNotation,
} from "@/plugins/molplot/scalar-format";
import { filterSpikes, smoothEma } from "@/plugins/molplot/smoothing";

/**
 * Coord-driven run-metrics view: reads the attempt's own files for the run named by
 * its explicit `{projectId, experimentId, runId}` props and renders a molplot
 * line chart per scalar series, plus one card per key of every other record
 * type (histogram, text, JSON, image). It deliberately takes explicit coordinates
 * rather than resolving the run from a workspace tree — so every consumer (the
 * workspace-explorer `RunMetricsTab` wrapper and the runs-dashboard
 * `RunInspector`) supplies the run identity it already holds directly.
 *
 * The pure builders (`buildScalarSeries`, `groupSeries`, `buildLineChartConfig`)
 * are exported for unit testing under the repo's node test environment.
 */

type XMode = "step" | "wall";
type YScale = "linear" | "log";

interface ScalarPoint {
  step: number;
  wall: number;
  y: number;
}

export interface ScalarSeries {
  key: string;
  group: string;
  points: ScalarPoint[];
  latest: number;
  /** Attempts some of these points were replayed from by the node cache. */
  replayedFrom?: string[];
}

export interface RunMetricsViewProps {
  status?: string;
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
  /** Open one of the attempt's images (attempt-relative path) in the image viewer. */
  onOpenImage?: (path: string) => void;
}

const isFiniteNumber = (value: unknown): value is number => {
  return typeof value === "number" && Number.isFinite(value);
};

const parseWall = (raw?: string): number => {
  if (!raw) return Number.NaN;
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : Number.NaN;
};

export const buildScalarSeries = (records: MetricRecord[]): ScalarSeries[] => {
  const grouped = new Map<string, ScalarPoint[]>();
  const replays = new Map<string, Set<string>>();

  records.forEach((record, index) => {
    if (record.t !== "scalar" || !isFiniteNumber(record.v)) {
      return;
    }
    const source = replayedFromOf(record);
    if (source) {
      const sources = replays.get(record.k) ?? new Set<string>();
      sources.add(source);
      replays.set(record.k, sources);
    }
    const points = grouped.get(record.k) ?? [];
    const wall = parseWall(record.w);
    points.push({
      step: isFiniteNumber(record.s) ? record.s : index,
      wall: Number.isFinite(wall) ? wall : index,
      y: record.v,
    });
    grouped.set(record.k, points);
  });

  return Array.from(grouped.entries())
    .map(([key, points]) => {
      points.sort((a, b) => a.step - b.step);
      const slash = key.indexOf("/");
      const group = slash > 0 ? key.slice(0, slash) : "";
      const sources = replays.get(key);
      return {
        key,
        group,
        points,
        latest: points[points.length - 1]?.y ?? 0,
        ...(sources ? { replayedFrom: [...sources].sort() } : {}),
      };
    })
    .sort((left, right) => left.key.localeCompare(right.key));
};

export const groupSeries = (series: ScalarSeries[]): Array<[string, ScalarSeries[]]> => {
  const buckets = new Map<string, ScalarSeries[]>();
  for (const s of series) {
    const list = buckets.get(s.group) ?? [];
    list.push(s);
    buckets.set(s.group, list);
  }
  return Array.from(buckets.entries()).sort(([a], [b]) => a.localeCompare(b));
};

// Exported so the multi-run aggregation view (aggregateSeries.ts) cycles the
// same 8 colors across runs that the single-run view cycles across series.
/** Categorical series colors (chart freedom; not run-status tokens). */
export const PALETTE = CHART_SERIES_PALETTE;

interface ChartConfigOptions {
  xMode: XMode;
  yScale: YScale;
  smoothing: number;
  color: string;
  /** Drop isolated outliers (Hampel/MAD) before EMA. */
  spikeFilter?: boolean;
  /** Modified-Z threshold in σ units. Lower = more aggressive. */
  spikeSigma?: number;
}

// Opacity applied to the raw signal trace when a smoothed overlay is drawn on
// top of it, so the smoothed curve reads as the primary line and the raw noise
// recedes into the background.
const RAW_TRACE_OPACITY = 0.3;

export const buildLineChartConfig = (series: ScalarSeries, options: ChartConfigOptions) => {
  const { xMode, yScale, smoothing, color, spikeFilter = false, spikeSigma = 4 } = options;
  const xs = series.points.map((p) => (xMode === "step" ? p.step : p.wall));
  const ys = series.points.map((p) => p.y);
  const cleaned = spikeFilter ? filterSpikes(ys, { nSigma: spikeSigma }) : ys;
  const processed = smoothing > 0 ? smoothEma(cleaned, smoothing) : cleaned;
  const overlay = spikeFilter || smoothing > 0;
  // Restore the two-trace overlay (faded raw behind the processed curve) — the
  // migration to a single series hid noise that smoothing / spike-filter is
  // meant to reveal vs. the raw signal. Filter always runs before EMA.
  const seriesList = overlay
    ? [
        {
          id: `${series.key}::raw`,
          label: "raw",
          color,
          width: 1,
          opacity: RAW_TRACE_OPACITY,
          initialPoints: ys.map((y, i) => ({ x: xs[i], y })),
        },
        {
          id: series.key,
          label: series.key,
          color,
          width: 2,
          initialPoints: processed.map((y, i) => ({ x: xs[i], y })),
        },
      ]
    : [
        {
          id: series.key,
          label: series.key,
          color,
          mode: "lines+markers" as const,
          initialPoints: ys.map((y, i) => ({ x: xs[i], y })),
        },
      ];
  return {
    series: seriesList,
    xAxis: {
      label: xMode === "step" ? "step" : "wall time",
      type: "linear" as const,
    },
    yAxis: { type: yScale, label: series.key },
    hovertemplate: "%{y:.6g}<extra></extra>",
    hovermode: "x unified" as const,
    theme: "auto" as const,
  };
};

interface ChartProps {
  series: ScalarSeries;
  xMode: XMode;
  yScale: YScale;
  smoothing: number;
  spikeFilter: boolean;
  spikeSigma: number;
  color: string;
  height: string;
  /** Where to put the legend, if this surface has room for one. */
  legend?: ChartLegendPlacement;
}

const MetricChart = ({
  series,
  xMode,
  yScale,
  smoothing,
  spikeFilter,
  spikeSigma,
  color,
  height,
  legend,
}: ChartProps): JSX.Element => {
  const config = useMemo(
    () =>
      buildLineChartConfig(series, {
        xMode,
        yScale,
        smoothing,
        spikeFilter,
        spikeSigma,
        color,
      }),
    [series, xMode, yScale, smoothing, spikeFilter, spikeSigma, color],
  );

  return (
    <MolplotLineChart
      config={config}
      style={{ width: "100%", height }}
      overlay={
        legend ? (
          // `minEntries={1}` on purpose: with smoothing off there is one
          // trace, and naming it is still what says this corner is the
          // legend — a legend that comes and goes with the smoothing slider
          // reads as a glitch.
          <ChartLegend series={config.series} placement={legend} minEntries={1} />
        ) : null
      }
    />
  );
};

interface CardSettings {
  notation: ScalarNotation;
  significantDigits: number;
  smoothing: number;
  spikeFilter: boolean;
  spikeSigma: number;
  xMode: XMode;
  yScale: YScale;
}

const DEFAULT_CARD_SETTINGS: CardSettings = {
  notation: DEFAULT_SCALAR_FORMAT.notation,
  significantDigits: DEFAULT_SCALAR_FORMAT.significantDigits,
  smoothing: 0.6,
  spikeFilter: false,
  spikeSigma: 4,
  xMode: "step",
  yScale: "linear",
};

const settingsOf = (map: Record<string, CardSettings>, key: string): CardSettings => ({
  ...DEFAULT_CARD_SETTINGS,
  ...map[key],
});

const scalarFormatOf = (settings: CardSettings): ScalarFormat => ({
  notation: settings.notation,
  significantDigits: settings.significantDigits,
});

const isPlotSeries = (series: ScalarSeries): boolean => series.points.length > 1;

interface MetricPanelProps {
  series: ScalarSeries;
  settings: CardSettings;
  color: string;
  selected: boolean;
  onSelect: () => void;
}

/**
 * One scalar series tile. The header selects it for Display; the Vega
 * container owns pan/zoom and must not sit under a click-capture layer.
 */
const MetricPanel = ({
  series,
  settings,
  color,
  selected,
  onSelect,
}: MetricPanelProps): JSX.Element => {
  const [enlarged, setEnlarged] = useState(false);
  const formatted = formatScalar(series.latest, scalarFormatOf(settings));
  const frameClass = cn(
    "relative min-w-0 bg-transparent p-3 text-left outline-none",
    "text-muted-foreground hover:text-foreground",
    "after:absolute after:inset-x-3 after:bottom-0 after:h-px after:bg-accent after:opacity-0 after:transition-opacity",
    selected && "text-accent after:opacity-100",
  );

  if (!isPlotSeries(series)) {
    return (
      <button
        type="button"
        className={cn(frameClass, "block w-full")}
        aria-pressed={selected}
        onClick={onSelect}
      >
        <div className="flex items-center gap-2">
          <span className="min-w-0 truncate text-micro font-medium">{series.key}</span>
          <ReplayMarker sources={series.replayedFrom ?? []} />
        </div>
        <div className="mt-1 font-mono text-display font-semibold tabular-nums">{formatted}</div>
      </button>
    );
  }

  return (
    <article className={frameClass} data-selected={selected || undefined}>
      <div className="flex cursor-pointer items-baseline justify-between gap-3">
        <button
          type="button"
          className="min-w-0 flex-1 truncate bg-transparent px-0 text-left text-body-lg font-medium"
          aria-pressed={selected}
          onClick={onSelect}
        >
          {series.key}
        </button>
        <div className="flex shrink-0 items-center gap-2">
          <ReplayMarker sources={series.replayedFrom ?? []} />
          <span className="font-mono text-label">{formatted}</span>
          <WorkbenchIconAction
            onClick={() => setEnlarged(true)}
            label="Enlarge chart"
            className="size-6 text-muted-foreground"
          >
            <Maximize2 className="size-icon-sm" />
          </WorkbenchIconAction>
        </div>
      </div>
      <div className="relative mt-1 min-h-0" onPointerDown={(event) => event.stopPropagation()}>
        <MetricChart
          series={series}
          xMode={settings.xMode}
          yScale={settings.yScale}
          smoothing={settings.smoothing}
          spikeFilter={settings.spikeFilter}
          spikeSigma={settings.spikeSigma}
          color={color}
          height="220px"
        />
      </div>
      <Dialog open={enlarged} onOpenChange={setEnlarged}>
        <DialogContent
          className={cn(
            "flex h-auto min-h-60 min-w-80 flex-col overflow-hidden p-4",
            "aspect-[4/3] w-[min(80vw,calc(90vh*4/3))] max-h-[90vh]",
            "max-w-[min(95vw,calc(90vh*4/3))] sm:max-w-[min(95vw,calc(90vh*4/3))]",
            "resize-x",
          )}
        >
          <DialogHeader className="shrink-0 pr-8">
            <DialogTitle className="truncate font-mono text-body-lg">{series.key}</DialogTitle>
          </DialogHeader>
          <div className="relative min-h-0 flex-1">
            <MetricChart
              series={series}
              xMode={settings.xMode}
              yScale={settings.yScale}
              smoothing={settings.smoothing}
              spikeFilter={settings.spikeFilter}
              spikeSigma={settings.spikeSigma}
              color={color}
              height="100%"
              legend="overlay"
            />
            <div
              className="pointer-events-none absolute right-1 bottom-1 h-2.5 w-2.5 border-r-2 border-b-2 border-muted-foreground/50"
              aria-hidden
            />
          </div>
        </DialogContent>
      </Dialog>
    </article>
  );
};

interface DisplayPatch {
  onChange: (patch: Partial<CardSettings>) => void;
}

const ScalarDisplayControls = ({
  settings,
  onChange,
}: DisplayPatch & { settings: CardSettings }): JSX.Element => (
  <div className="flex flex-col gap-4 text-label">
    <div className="flex flex-col gap-2">
      <Label htmlFor="metric-notation">Notation</Label>
      <Select
        value={settings.notation}
        onValueChange={(value) => onChange({ notation: value as ScalarNotation })}
      >
        <SelectTrigger id="metric-notation" className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="auto">Auto</SelectItem>
          <SelectItem value="scientific">Scientific</SelectItem>
          <SelectItem value="decimal">Decimal</SelectItem>
        </SelectContent>
      </Select>
    </div>
    <div className="flex flex-col gap-2">
      <span className="font-medium text-foreground">Significant digits</span>
      <div className="flex items-center gap-2">
        <Slider
          min={1}
          max={8}
          step={1}
          value={[settings.significantDigits]}
          onValueChange={([value]) => onChange({ significantDigits: value })}
          className="flex-1"
          aria-label="Significant digits"
        />
        <span className="w-control text-right font-mono tabular-nums text-muted-foreground">
          {settings.significantDigits}
        </span>
      </div>
    </div>
  </div>
);

const PlotDisplayControls = ({
  settings,
  onChange,
}: DisplayPatch & { settings: CardSettings }): JSX.Element => (
  <div className="flex flex-col gap-4 text-label">
    <div className="flex flex-col gap-2">
      <span className="font-medium text-foreground">Smoothing</span>
      <div className="flex items-center gap-2">
        <Slider
          min={0}
          max={0.99}
          step={0.01}
          value={[settings.smoothing]}
          onValueChange={([value]) => onChange({ smoothing: value })}
          className="flex-1"
          aria-label="TensorBoard EMA smoothing"
        />
        <span className="w-control text-right font-mono tabular-nums text-muted-foreground">
          {settings.smoothing.toFixed(2)}
        </span>
      </div>
      <p className="text-micro text-muted-foreground">
        TensorBoard-style EMA. 0 is raw; 0.6 is the usual default.
      </p>
    </div>
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="metric-spike-filter" className="font-medium text-foreground">
          Filter spikes
        </Label>
        <Switch
          id="metric-spike-filter"
          checked={settings.spikeFilter}
          onCheckedChange={(checked) => onChange({ spikeFilter: checked })}
          aria-label="Filter outlier spikes before smoothing"
        />
      </div>
      <p className="text-micro text-muted-foreground">
        Drop isolated outliers, then smooth. A glitch cannot yank the EMA.
      </p>
      {settings.spikeFilter ? (
        <div className="flex flex-col gap-2">
          <span className="font-medium text-foreground">Threshold (σ)</span>
          <div className="flex items-center gap-2">
            <Slider
              min={2}
              max={8}
              step={0.5}
              value={[settings.spikeSigma]}
              onValueChange={([value]) => onChange({ spikeSigma: value })}
              className="flex-1"
              aria-label="Spike filter threshold in sigma"
            />
            <span className="w-control text-right font-mono tabular-nums text-muted-foreground">
              {settings.spikeSigma.toFixed(1)}
            </span>
          </div>
          <p className="text-micro text-muted-foreground">Lower catches more spikes.</p>
        </div>
      ) : null}
    </div>
    <div className="flex flex-col gap-2">
      <span className="font-medium text-foreground">X axis</span>
      <div className="grid grid-cols-2 gap-1">
        {(["step", "wall"] as const).map((mode) => (
          <WorkbenchAction
            key={mode}
            kind={settings.xMode === mode ? "primary" : "secondary"}
            size="compact"
            onClick={() => onChange({ xMode: mode })}
            className="w-full"
          >
            {mode === "step" ? "Step" : "Wall"}
          </WorkbenchAction>
        ))}
      </div>
    </div>
    <div className="flex flex-col gap-2">
      <span className="font-medium text-foreground">Y axis</span>
      <div className="grid grid-cols-2 gap-1">
        {(["linear", "log"] as const).map((scale) => (
          <WorkbenchAction
            key={scale}
            kind={settings.yScale === scale ? "primary" : "secondary"}
            size="compact"
            onClick={() => onChange({ yScale: scale })}
            className="w-full"
          >
            {scale === "linear" ? "Linear" : "Log"}
          </WorkbenchAction>
        ))}
      </div>
    </div>
  </div>
);

export const RunMetricsView = ({
  projectId,
  experimentId,
  runId,
  executionId,
  status,
  onOpenImage,
}: RunMetricsViewProps): JSX.Element => {
  const {
    data: { records, sources },
    error,
  } = useSuspenseQuery({
    queryKey: runKeys.metrics(projectId, experimentId, runId, executionId),
    queryFn: () =>
      readExecutionMetrics(
        { projectId, experimentId, runId, executionId },
        { stepInterval: STEP_INTERVAL },
      ),
    refetchInterval: journalRefetchInterval(status),
    refetchIntervalInBackground: false,
  });
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [cardSettings, setCardSettings] = useState<Record<string, CardSettings>>({});
  const [taskFilter, setTaskFilter] = useState<string | null>(null);

  const tasks = useMemo(() => listTasks(records), [records]);
  // A task that no longer appears (another attempt, another read) is no filter.
  const task = taskFilter !== null && tasks.includes(taskFilter) ? taskFilter : null;
  const visible = useMemo(() => filterByTask(records, task), [records, task]);
  const cards = useMemo(() => buildMetricCards(visible), [visible]);
  const scalarSeries = useMemo(() => buildScalarSeries(cards.scalars), [cards.scalars]);
  const grouped = useMemo(() => groupSeries(scalarSeries), [scalarSeries]);
  const selectedSeries = scalarSeries.find((item) => item.key === selectedKey) ?? null;

  if (error && records.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<AlertTriangle className="h-6 w-6" />}
          title="Metrics unavailable"
          description={error instanceof Error ? error.message : "Failed to read metrics"}
        />
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<Activity className="h-6 w-6" />}
          title="No metrics recorded"
          description="This run has not written metrics yet."
        />
      </div>
    );
  }

  const selectCard = (key: string): void => {
    setSelectedKey(key);
    setPanelOpen(true);
  };

  const patchSelected = (patch: Partial<CardSettings>): void => {
    if (!selectedKey) return;
    setCardSettings((current) => ({
      ...current,
      [selectedKey]: { ...settingsOf(current, selectedKey), ...patch },
    }));
  };

  const settings = selectedSeries ? (
    <>
      <p className="truncate font-mono text-label text-muted-foreground">{selectedSeries.key}</p>
      {isPlotSeries(selectedSeries) ? (
        <PlotDisplayControls
          settings={settingsOf(cardSettings, selectedSeries.key)}
          onChange={patchSelected}
        />
      ) : (
        <ScalarDisplayControls
          settings={settingsOf(cardSettings, selectedSeries.key)}
          onChange={patchSelected}
        />
      )}
    </>
  ) : (
    <p className="text-label text-muted-foreground">Select a metric to format it.</p>
  );

  const otherCards =
    cards.histograms.length + cards.images.length + cards.texts.length + cards.jsons.length;

  const readSummary = (
    <>
      <span>{records.length} records</span>
      <span>{scalarSeries.length} scalars</span>
      {cards.histograms.length > 0 && <span>{cards.histograms.length} histograms</span>}
      {cards.images.length > 0 && <span>{cards.images.length} image keys</span>}
      {cards.texts.length > 0 && <span>{cards.texts.length} text keys</span>}
      {cards.jsons.length > 0 && <span>{cards.jsons.length} JSON keys</span>}
      {sources.length > 0 && (
        <span>
          {sources.length} source{sources.length === 1 ? "" : "s"}:{" "}
          {sources.map((item) => item.label).join(", ")}
        </span>
      )}
      {sources.some((item) => item.error) && (
        <span>{sources.filter((item) => item.error).length} unreadable</span>
      )}
    </>
  );

  return (
    <ChartWorkbench settings={settings} open={panelOpen} onOpenChange={setPanelOpen}>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <DashboardCanvas>
          <p className="flex flex-wrap gap-x-3 font-mono text-micro tabular-nums text-muted-foreground">
            {readSummary}
          </p>
          {tasks.length > 0 ? (
            <TaskFilter tasks={tasks} value={task} onChange={setTaskFilter} />
          ) : null}
          {grouped.length > 0 ? (
            grouped.map(([groupName, items]) => (
              <OverviewSection key={groupName || "_root"} title={groupName ? groupName : "Scalars"}>
                <div className="grid gap-3 lg:grid-cols-2">
                  {items.map((series, index) => (
                    <MetricPanel
                      key={series.key}
                      series={series}
                      settings={settingsOf(cardSettings, series.key)}
                      color={PALETTE[index % PALETTE.length]}
                      selected={selectedKey === series.key}
                      onSelect={() => selectCard(series.key)}
                    />
                  ))}
                </div>
              </OverviewSection>
            ))
          ) : otherCards === 0 ? (
            <OverviewSection title="Scalars">
              <div className="border-y border-dashed border-border/70 py-6 text-center text-body-lg text-muted-foreground">
                {task ? `No metrics recorded by ${task}.` : "No scalar metrics recorded."}
              </div>
            </OverviewSection>
          ) : null}

          {cards.histograms.length > 0 && (
            <OverviewSection title="Histograms">
              <div className="grid gap-3 lg:grid-cols-2">
                {cards.histograms.map((card, index) => (
                  <HistogramCard
                    key={card.key}
                    card={card}
                    color={PALETTE[index % PALETTE.length]}
                  />
                ))}
              </div>
            </OverviewSection>
          )}
          {cards.images.length > 0 && (
            <OverviewSection title="Images">
              <div className="grid gap-3">
                {cards.images.map((card) => (
                  <ImageCard
                    key={card.key}
                    card={card}
                    coords={{ projectId, experimentId, runId, executionId }}
                    onOpenImage={onOpenImage}
                  />
                ))}
              </div>
            </OverviewSection>
          )}
          {cards.texts.length > 0 && (
            <OverviewSection title="Text">
              <div className="grid gap-3 lg:grid-cols-2">
                {cards.texts.map((card) => (
                  <TextCard key={card.key} card={card} />
                ))}
              </div>
            </OverviewSection>
          )}
          {cards.jsons.length > 0 && (
            <OverviewSection title="JSON">
              <div className="grid gap-3 lg:grid-cols-2">
                {cards.jsons.map((card) => (
                  <JsonCard key={card.key} card={card} />
                ))}
              </div>
            </OverviewSection>
          )}
        </DashboardCanvas>
      </div>
    </ChartWorkbench>
  );
};
