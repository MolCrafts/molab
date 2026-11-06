import type { BarChartConfig } from "@molcrafts/molplot";
import { useSuspenseQuery } from "@tanstack/react-query";
import type { JSX } from "react";
import { useMemo } from "react";
import { runFileTextQueryOptions } from "@/app/state/entityQueries";
import type { RendererProps } from "@/app/types";
import { DELTA_F_GROUP_COLORS } from "@/lib/chart-tokens";
import { MolplotBarChart } from "@/plugins/molplot";
import type { DiscoveredFile } from "@/plugins/types";

type DeltaFTabProps = RendererProps & { discoveredFiles?: DiscoveredFile[] };

interface DeltaFStats {
  comp_rms_mev_A: number;
  atom_rms_mev_A: number;
  max_mev_A: number;
  pct_of_Frms: number;
}

interface DeltaFReport {
  gold_standard?: string;
  eval_configs?: number;
  dataset_force_rms_mev_A?: number;
  deltaF: Record<string, DeltaFStats>;
}

// Stable display order + human labels for the ΔF decomposition keys produced
// by eval_df.compute_deltaF (phase1).
// Bars grouped by effect type. Scientific series palette (oklch categorical —
// not brand/status tokens). Short tick labels (long ones need `automargin`,
// which oscillates margins on zoom → jitter); full description in hover.
// Each tuple = [reportKey, tick, hover].
type Member = readonly [string, string, string];
const GROUPS: ReadonlyArray<{
  id: string;
  label: string;
  color: string;
  members: ReadonlyArray<Member>;
}> = [
  {
    id: "inference",
    label: "inference (bf16 forward)",
    color: DELTA_F_GROUP_COLORS.inference,
    members: [
      ["infer_effect_on_fp32w", "infer·fp32w", "inference bf16, fp32 weights"],
      ["infer_effect_on_bf16w", "infer·bf16w", "inference bf16, bf16 weights"],
    ],
  },
  {
    id: "training",
    label: "training precision",
    color: DELTA_F_GROUP_COLORS.training,
    members: [
      ["train_effect_fp64", "train·fp64", "fp64 training vs fp32"],
      ["train_effect_bf16", "train·bf16", "bf16 training vs fp32"],
    ],
  },
  {
    id: "combined",
    label: "combined / reference",
    color: DELTA_F_GROUP_COLORS.combined,
    members: [
      ["combined_e2e_bf16", "e2e·bf16", "combined end-to-end bf16"],
      ["fp64_native_vs_gold", "fp64·native", "fp64 native vs gold"],
    ],
  },
];

/**
 * Auto-discovered run tab for the Phase-1 ΔF report (`phase1_df_report.json`).
 * Renders the per-component force-deviation decomposition (vs the fp32 gold
 * standard) as a molplot bar chart; hover shows the % of the dataset force RMS.
 */
export const DeltaFChart = ({
  selection,
  snapshot,
  discoveredFiles,
  executionId,
}: DeltaFTabProps): JSX.Element => {
  const run = snapshot.runs.find((item) => item.id === selection.objectId);
  if (!run || !executionId)
    return <div className="p-4 text-label text-muted-foreground">Select an execution.</div>;
  return (
    <DeltaFReportChart
      projectId={run.projectId}
      experimentId={run.experimentId}
      runId={run.id}
      executionId={executionId}
      path={discoveredFiles?.[0]?.relPath ?? "phase1_df_report.json"}
    />
  );
};

const DeltaFReportChart = ({
  projectId,
  experimentId,
  runId,
  executionId,
  path,
}: {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
  path: string;
}): JSX.Element => {
  const { data: report } = useSuspenseQuery({
    ...runFileTextQueryOptions(projectId, experimentId, runId, executionId, path),
    select: (content) => JSON.parse(content) as DeltaFReport,
  });
  const config = useMemo<BarChartConfig | null>(() => {
    if (!report?.deltaF) {
      return null;
    }
    const series = GROUPS.map((group) => ({
      id: group.id,
      label: group.label,
      color: group.color,
      points: group.members
        .filter(([key]) => report.deltaF[key] != null)
        .map(([key, label, desc]) => {
          const stat = report.deltaF[key];
          return {
            x: label,
            y: stat.comp_rms_mev_A,
            // NOTE: deliberately no `text` — molplot renders point.text ON the
            // bar with auto-shrunk font (unreadable on small bars). Values are
            // read off the (enlarged) y-axis; full detail is in the hover via
            // customdata.
            customdata: `${desc}: ${stat.comp_rms_mev_A.toFixed(1)} meV/Å · ${stat.pct_of_Frms.toFixed(2)}% of F_rms`,
          };
        }),
      hovertemplate: "%{customdata}<extra></extra>",
    })).filter((s) => s.points.length > 0);
    return {
      series,
      // overlay (not group): categories are disjoint across series, so each bar
      // centres at its own tick instead of being offset within a cluster.
      mode: "overlay",
      xAxis: { label: "", tickfont: { size: 13 } },
      yAxis: { label: "ΔF (meV/Å)", rangemode: "tozero", tickfont: { size: 13 } },
      showLegend: true,
    };
  }, [report]);

  if (!config) {
    return (
      <div className="p-4 text-body-lg text-muted-foreground">
        The ΔF report contains no decomposition.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 p-4">
      <div className="text-body-lg text-muted-foreground">
        Gold standard: {report?.gold_standard} · {report?.eval_configs} configs · F_rms ={" "}
        {report?.dataset_force_rms_mev_A} meV/Å
      </div>
      {/* Fixed height (not flex-1/100%) so the chart's autosize can't feed back
          into a resizing flex parent — the same stable pattern the metrics tab
          uses. */}
      <MolplotBarChart
        config={config}
        style={{ width: "100%", height: "var(--spacing-chart-xl)" }}
      />
    </div>
  );
};
