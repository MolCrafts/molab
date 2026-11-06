import { Input } from "@molcrafts/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";
import { type JSX, useMemo, useState } from "react";
import type { TensorboardScalarSeries } from "@/api";
import { tensorboardApi } from "@/api";
import { DashboardCanvas, EmptyState, OverviewSection } from "@/app/components/entity";
import { runKeys } from "@/app/state/entityQueries";
import type { RendererProps } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { MolplotLineChart } from "@/plugins/molplot";
import type { DiscoveredFile } from "@/plugins/types";

type TensorBoardTabProps = RendererProps & { discoveredFiles?: DiscoveredFile[] };

const formatValue = (value: number): string => {
  if (!Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1000 || (abs > 0 && abs < 0.001)) return value.toExponential(3);
  return value.toPrecision(4);
};

interface SeriesCardProps {
  series: TensorboardScalarSeries;
  xMode: "step" | "wall";
  yScale: "linear" | "log";
}

const SeriesCard = ({ series, xMode, yScale }: SeriesCardProps): JSX.Element => {
  const config = useMemo(
    () => ({
      series: [
        {
          id: series.tag,
          label: series.tag,
          initialPoints: series.points.map((p) => ({
            x: xMode === "step" ? p.step : p.wallTime * 1000,
            y: p.value,
          })),
        },
      ],
      xAxis: {
        label: xMode === "step" ? "step" : "wall time",
        type: xMode === "wall" ? ("linear" as const) : ("linear" as const),
      },
      yAxis: {
        label: series.tag,
        type: yScale,
      },
      modebar: true,
      theme: "auto" as const,
    }),
    [series, xMode, yScale],
  );

  const latest = series.points[series.points.length - 1]?.value ?? 0;
  return (
    <section className="min-w-0 rounded-control border border-border bg-background p-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-body-lg font-medium text-foreground">{series.tag}</div>
          <div className="font-mono text-micro text-muted-foreground">
            {series.points.length} pts · {series.logdir || "."}
          </div>
        </div>
        <div className="font-mono text-label text-muted-foreground">{formatValue(latest)}</div>
      </div>
      <MolplotLineChart
        config={config}
        style={{ width: "100%", height: "var(--spacing-chart-md)" }}
      />
    </section>
  );
};

const groupByPrefix = (
  series: TensorboardScalarSeries[],
): Array<[string, TensorboardScalarSeries[]]> => {
  const buckets = new Map<string, TensorboardScalarSeries[]>();
  for (const s of series) {
    const slash = s.tag.indexOf("/");
    const group = slash > 0 ? s.tag.slice(0, slash) : "";
    const list = buckets.get(group) ?? [];
    list.push(s);
    buckets.set(group, list);
  }
  return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b));
};

export const TensorBoardTab = ({ selection, snapshot }: TensorBoardTabProps): JSX.Element => {
  const run = snapshot.runs.find((r) => r.id === selection.objectId);
  if (!run) return <EmptyState title="Run not found" />;
  return (
    <TensorBoardScalars projectId={run.projectId} experimentId={run.experimentId} runId={run.id} />
  );
};

const TensorBoardScalars = ({
  projectId,
  experimentId,
  runId,
}: {
  projectId: string;
  experimentId: string;
  runId: string;
}): JSX.Element => {
  const { data } = useSuspenseQuery({
    queryKey: runKeys.tensorboard(projectId, experimentId, runId),
    queryFn: () => tensorboardApi.getRunTensorboardScalars(projectId, experimentId, runId),
  });
  const [search, setSearch] = useState("");
  const [xMode, setXMode] = useState<"step" | "wall">("step");
  const [yScale, setYScale] = useState<"linear" | "log">("linear");
  const filtered = search
    ? data.series.filter((s) => s.tag.toLowerCase().includes(search.toLowerCase()))
    : data.series;
  const grouped = groupByPrefix(filtered);

  return (
    <div className="min-h-0 flex-1 overflow-auto bg-background">
      <DashboardCanvas>
        <p className="font-mono text-micro tabular-nums text-muted-foreground">
          {data.logdirs.length} logdirs · {data.series.length} series
        </p>

        <div className="flex flex-wrap items-center gap-3 border-b border-border py-2 text-label">
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter tags"
            className="h-control-compact w-56 text-label"
          />
          <div className="flex items-center gap-1">
            <span className="font-medium text-foreground">X</span>
            {(["step", "wall"] as const).map((mode) => (
              <WorkbenchAction
                key={mode}
                kind={xMode === mode ? "primary" : "ghost"}
                size="compact"
                onClick={() => setXMode(mode)}
                className="h-6 px-2"
              >
                {mode === "step" ? "Step" : "Wall"}
              </WorkbenchAction>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <span className="font-medium text-foreground">Y</span>
            {(["linear", "log"] as const).map((scale) => (
              <WorkbenchAction
                key={scale}
                kind={yScale === scale ? "primary" : "ghost"}
                size="compact"
                onClick={() => setYScale(scale)}
                className="h-6 px-2"
              >
                {scale === "linear" ? "Linear" : "Log"}
              </WorkbenchAction>
            ))}
          </div>
        </div>

        {data.series.length === 0 ? (
          <EmptyState
            icon={<BarChart3 className="h-6 w-6" />}
            title="No scalars found"
            description={`Discovered ${data.logdirs.length} logdir(s) but no scalar tags.`}
          />
        ) : grouped.length === 0 ? (
          <OverviewSection title="Scalars">
            <div className="rounded-control border border-dashed border-border px-3 py-6 text-center text-body-lg text-muted-foreground">
              No tags match the current filter.
            </div>
          </OverviewSection>
        ) : (
          grouped.map(([groupName, items]) => (
            <OverviewSection key={groupName || "_root"} title={groupName || "Scalars"}>
              <div className="grid gap-3 lg:grid-cols-2">
                {items.map((series) => (
                  <SeriesCard
                    key={`${series.logdir}::${series.tag}`}
                    series={series}
                    xMode={xMode}
                    yScale={yScale}
                  />
                ))}
              </div>
            </OverviewSection>
          ))
        )}
      </DashboardCanvas>
    </div>
  );
};
