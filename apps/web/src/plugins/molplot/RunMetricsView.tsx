import { Activity, AlertTriangle, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, OverviewSection } from "@/app/components/entity";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
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
import { readExecutionMetrics, type SourceRead } from "@/plugins/molplot/read-metrics";
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
 * line chart per scalar series. It deliberately takes explicit coordinates
 * rather than resolving the run from a workspace tree — so every consumer (the
 * workspace-explorer `RunMetricsTab` wrapper and the runs-dashboard
 * `RunInspector`) supplies the run identity it already holds directly.
 *
 * The pure builders (`buildScalarSeries`, `groupSeries`, `buildLineChartConfig`)
 * are exported for unit testing under the repo's node test environment.
 */
const POLL_INTERVAL_MS = 1500;

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
}

export interface RunMetricsViewProps {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
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

  records.forEach((record, index) => {
    if (record.t !== "scalar" || !isFiniteNumber(record.v)) {
      return;
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
      return {
        key,
        group,
        points,
        latest: points[points.length - 1]?.y ?? 0,
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
        <div className="truncate text-micro font-medium">{series.key}</div>
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

const OtherRecords = ({ records }: { records: MetricRecord[] }): JSX.Element | null => {
  const nonScalar = records.filter((record) => record.t !== "scalar").slice(-20);
  if (nonScalar.length === 0) {
    return null;
  }

  return (
    <OverviewSection title="Other Events">
      <div className="divide-y divide-border border-y border-border">
        {nonScalar.map((record) => (
          <div
            key={`${record.k}:${record.t}:${record.s ?? ""}:${record.w ?? ""}`}
            className="grid gap-1 px-3 py-2 text-body-lg md:grid-cols-4"
          >
            <div className="min-w-0 font-medium text-foreground">{record.k}</div>
            <div className="text-muted-foreground">{record.t}</div>
            <div className="text-muted-foreground">{record.s ?? "-"}</div>
            <pre className="min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-label text-muted-foreground">
              {JSON.stringify(record.v)}
            </pre>
          </div>
        ))}
      </div>
    </OverviewSection>
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
}: RunMetricsViewProps): JSX.Element => {
  const [records, setRecords] = useState<MetricRecord[]>([]);
  const [sources, setSources] = useState<SourceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [cardSettings, setCardSettings] = useState<Record<string, CardSettings>>({});

  const scalarSeries = useMemo(() => buildScalarSeries(records), [records]);
  const grouped = useMemo(() => groupSeries(scalarSeries), [scalarSeries]);
  const selectedSeries = scalarSeries.find((item) => item.key === selectedKey) ?? null;

  // What was read last time, so a poll that finds nothing new can skip the
  // work. Held in a ref rather than a dependency: keying the effect on it
  // would tear down the interval after every successful read and collapse
  // POLL_INTERVAL_MS into a tight loop.
  const lastRevisionsRef = useRef<string>("");

  // The fetch effect re-keys on the run coords; callers also mount this view
  // with `key={runId}` so a run switch remounts it with fresh state (cursor +
  // accumulator), rather than threading a manual reset effect.
  useEffect(() => {
    let cancelled = false;

    const fetchMetrics = async (): Promise<void> => {
      try {
        // The server lists the attempt's files and hands back bytes; every
        // decision about what is plottable and what the numbers mean happens
        // here, through whichever reader claimed the file.
        const read = await readExecutionMetrics(
          { projectId, experimentId, runId, executionId },
          { stepInterval: STEP_INTERVAL },
        );
        if (cancelled) {
          return;
        }
        // A finished log re-reads to the same bytes; only re-render when a
        // source actually moved.
        const revisions = read.sources.map((item) => `${item.path}@${item.revision}`).join("|");
        if (revisions !== lastRevisionsRef.current) {
          lastRevisionsRef.current = revisions;
          setRecords(read.records);
          setSources(read.sources);
        }
        setError(null);
      } catch (metricsError) {
        if (!cancelled) {
          setError(metricsError instanceof Error ? metricsError.message : "Failed to load metrics");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchMetrics();
    const intervalId = window.setInterval(() => {
      void fetchMetrics();
    }, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [executionId, projectId, experimentId, runId]);

  if (loading && records.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background text-body-lg text-muted-foreground">
        Loading metrics...
      </div>
    );
  }

  if (error && records.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<AlertTriangle className="h-6 w-6" />}
          title="Metrics unavailable"
          description={error}
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

  const readSummary = (
    <>
      <span>{records.length} records</span>
      <span>{scalarSeries.length} scalars</span>
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
    <ChartWorkbench
      settings={settings}
      settingsFooter={readSummary}
      open={panelOpen}
      onOpenChange={setPanelOpen}
    >
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-4 md:px-6">
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
          ) : (
            <OverviewSection title="Scalars">
              <div className="border-y border-dashed border-border/70 py-6 text-center text-body-lg text-muted-foreground">
                No scalar metrics recorded.
              </div>
            </OverviewSection>
          )}

          <OtherRecords records={records} />
        </div>
      </div>
    </ChartWorkbench>
  );
};
