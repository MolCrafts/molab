/**
 * Every WAL record type gets its own card (D93): scalars keep their series
 * tiles; histogram, text, JSON and image records each get one card per key.
 */

import { beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { runsApi, workspaceApi } from "@/api";
import { runKeys } from "@/app/state/entityQueries";
import type { MetricRecordSample as MetricRecord } from "@/lib/contribution-types";
import { imageBlobQueryOptions } from "./MetricCards";
import {
  buildHistogramBarConfig,
  buildMetricCards,
  countMetricKeys,
  filterByTask,
  isAttemptRelative,
  listTasks,
} from "./metric-cards";
import { buildScalarSeries, RunMetricsView } from "./RunMetricsView";
import { resolveMolplotMetricsTabBadgeCount } from "./tab-badge-count";

rs.mock("@/api", () => ({
  runsApi: { getRunFiles: rs.fn(), getRunFileText: rs.fn() },
  workspaceApi: { getWorkspaceFileBlob: rs.fn() },
  assetsApi: {},
  projectsApi: {},
}));

rs.mock("@/plugins/molplot/read-metrics", () => ({ readExecutionMetrics: rs.fn() }));

const coords = { projectId: "p", experimentId: "x", runId: "r", executionId: "e02" };

const WAL: MetricRecord[] = [
  { t: "scalar", k: "loss", s: 0, v: 1.0, tags: { task: "train" } },
  { t: "scalar", k: "loss", s: 1, v: 0.5, tags: { task: "train" } },
  {
    t: "scalar",
    k: "energy",
    s: 0,
    v: -3.2,
    tags: { task: "prepare", replayed_from: "e01" },
  },
  {
    t: "histogram",
    k: "forces",
    s: 99,
    v: { bins: [0, 0.5, 1], counts: [12, 3] },
    tags: { task: "train" },
  },
  {
    t: "histogram",
    k: "forces",
    s: 199,
    v: { bins: [0, 0.5, 1], counts: [10, 5] },
    tags: { task: "train" },
  },
  { t: "text", k: "note", s: 50, v: "lr halved at step 50", tags: { task: "train" } },
  { t: "text", k: "setup", v: "built 3 structures", tags: { task: "prepare" } },
  { t: "json", k: "config", v: { lr: 0.001, batch: 32 }, tags: { task: "prepare" } },
  {
    t: "image_ref",
    k: "rdf",
    s: 99,
    v: { path: "artifacts/rdf.png", caption: "g(r)" },
    tags: { task: "train" },
  },
];

const renderView = (records: MetricRecord[]) => {
  const client = new QueryClient();
  client.setQueryData(runKeys.metrics("p", "x", "r", "e02"), { records, sources: [] });
  const html = renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <RunMetricsView {...coords} status="succeeded" />
    </QueryClientProvider>,
  );
  return { client, html };
};

const count = (html: string, needle: string): number => html.split(needle).length - 1;

describe("RunMetricsView cards", () => {
  beforeEach(() => {
    rs.clearAllMocks();
  });

  it("renders one card of each kind for a WAL with all five record types", () => {
    const { html } = renderView(WAL);
    expect(html).toContain(">loss<");
    expect(html).toContain(">energy<");
    expect(count(html, 'data-card="histogram"')).toBe(1);
    expect(count(html, 'data-card="text"')).toBe(2);
    expect(count(html, 'data-card="json"')).toBe(1);
    expect(count(html, 'data-card="image"')).toBe(1);
    expect(html).toContain('data-key="forces"');
    expect(html).toContain("lr halved at step 50");
    expect(html).toContain("g(r)");
    // The raw "last 20 events" list is gone.
    expect(html).not.toContain("Other Events");
  });

  it("offers a task filter when records carry tags.task", () => {
    const { html } = renderView(WAL);
    expect(html).toContain('aria-label="Filter by task"');
    expect(html).toContain(">all<");
    expect(html).toContain(">prepare<");
    expect(html).toContain(">train<");
    const untagged = renderView(WAL.map(({ tags: _tags, ...record }) => record)).html;
    expect(untagged).not.toContain('aria-label="Filter by task"');
  });

  it("narrows every card type to one task", () => {
    expect(listTasks(WAL)).toEqual(["prepare", "train"]);
    const train = buildMetricCards(filterByTask(WAL, "train"));
    expect(buildScalarSeries(train.scalars).map((series) => series.key)).toEqual(["loss"]);
    expect(train.histograms.map((card) => card.key)).toEqual(["forces"]);
    expect(train.texts.map((card) => card.key)).toEqual(["note"]);
    expect(train.jsons).toEqual([]);
    expect(train.images.map((card) => card.key)).toEqual(["rdf"]);

    const prepare = buildMetricCards(filterByTask(WAL, "prepare"));
    expect(buildScalarSeries(prepare.scalars).map((series) => series.key)).toEqual(["energy"]);
    expect(prepare.histograms).toEqual([]);
    expect(prepare.texts.map((card) => card.key)).toEqual(["setup"]);
    expect(prepare.jsons.map((card) => card.key)).toEqual(["config"]);
    expect(prepare.images).toEqual([]);

    expect(filterByTask(WAL, null)).toHaveLength(WAL.length);
  });

  it("marks series and cards whose records were replayed from another attempt", () => {
    const { html } = renderView(WAL);
    expect(html).toContain("replayed from e01");
    expect(count(html, 'data-replayed-from="e01"')).toBe(1);
    const energy = buildScalarSeries(WAL).find((series) => series.key === "energy");
    expect(energy?.replayedFrom).toEqual(["e01"]);
    expect(buildScalarSeries(WAL).find((series) => series.key === "loss")?.replayedFrom).toBe(
      undefined,
    );

    const replayedImage = buildMetricCards([
      { ...WAL[WAL.length - 1], tags: { task: "train", replayed_from: "e01" } },
    ]);
    expect(replayedImage.images[0].replayedFrom).toEqual(["e01"]);
  });

  it("requests an image through the attempt's own file route, by its attempt-relative path", async () => {
    const { client } = renderView(WAL);
    const blobKey = runKeys.fileBlob("p", "x", "r", "e02", "artifacts/rdf.png");
    expect(client.getQueryCache().find({ queryKey: blobKey })).toBeDefined();

    rs.mocked(runsApi.getRunFiles).mockResolvedValue({
      runDir: "projects/a/experiments/b/runs/seed=1/executions/e02",
      nodes: [],
    } as unknown as Awaited<ReturnType<typeof runsApi.getRunFiles>>);
    const blob = new Blob(["png"]);
    rs.mocked(workspaceApi.getWorkspaceFileBlob).mockResolvedValue(blob);

    const fetched = await new QueryClient().fetchQuery(
      imageBlobQueryOptions(coords, "artifacts/rdf.png"),
    );

    expect(fetched).toBe(blob);
    expect(runsApi.getRunFiles).toHaveBeenCalledWith("p", "x", "r", "e02");
    expect(workspaceApi.getWorkspaceFileBlob).toHaveBeenCalledWith(
      "projects/a/experiments/b/runs/seed=1/executions/e02/artifacts/rdf.png",
    );
  });

  it("never fetches an image path outside the attempt", () => {
    expect(isAttemptRelative("artifacts/rdf.png")).toBe(true);
    expect(isAttemptRelative("/home/me/rdf.png")).toBe(false);
    expect(isAttemptRelative("../other/rdf.png")).toBe(false);
    expect(isAttemptRelative("C:\\data\\rdf.png")).toBe(false);
    const { client } = renderView([
      { t: "image_ref", k: "plot", s: 1, v: { path: "/tmp/plot.png", caption: null } },
    ]);
    expect(
      client
        .getQueryCache()
        .find({ queryKey: runKeys.fileBlob("p", "x", "r", "e02", "/tmp/plot.png") })?.state
        .fetchStatus ?? "idle",
    ).toBe("idle");
  });

  it("orders entries by step and draws the latest histogram by default", () => {
    const cards = buildMetricCards(WAL);
    const forces = cards.histograms[0];
    expect(forces.entries.map((entry) => entry.step)).toEqual([99, 199]);
    const config = buildHistogramBarConfig("forces", forces.entries[1].value, "red");
    expect(config.series[0].points.map((point) => point.y)).toEqual([10, 5]);
    expect(config.series[0].points.map((point) => point.x)).toEqual(["0–0.5", "0.5–1"]);
    const html = renderView(WAL).html;
    expect(html).toContain("step 199");
  });
});

describe("Metrics tab badge", () => {
  it("counts keys of every record type, not scalars only", async () => {
    const { readExecutionMetrics } = await import("@/plugins/molplot/read-metrics");
    rs.mocked(readExecutionMetrics).mockResolvedValue({ records: WAL, sources: [] });
    // loss, energy, forces, note, setup, config, rdf
    expect(countMetricKeys(WAL)).toBe(7);
    await expect(
      resolveMolplotMetricsTabBadgeCount({
        projectId: "p",
        experimentId: "x",
        runId: "r",
        executionId: "e02",
      } as Parameters<typeof resolveMolplotMetricsTabBadgeCount>[0]),
    ).resolves.toBe(7);

    rs.mocked(readExecutionMetrics).mockResolvedValue({
      records: [{ t: "image_ref", k: "rdf", s: 1, v: { path: "artifacts/a.png" } }],
      sources: [],
    });
    await expect(
      resolveMolplotMetricsTabBadgeCount({
        projectId: "p",
        experimentId: "x",
        runId: "r",
        executionId: "e02",
      } as Parameters<typeof resolveMolplotMetricsTabBadgeCount>[0]),
    ).resolves.toBe(1);
  });
});
