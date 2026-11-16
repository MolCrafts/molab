/**
 * An asset in its context (L08 v3): what made it and from what, who uses it.
 *
 * Every answer is read from two lists the app already loads: the asset
 * summaries (`AssetSummary.origin`) and the workspace run inventory
 * (`WorkspaceRunRow.inputs` / `parameters`). Nothing here fetches.
 */

import type { WorkspaceRunRow } from "@/app/runs/types";
import type { AssetSummary } from "@/app/types";
import { type AssetKind, kindOfAsset } from "./assetKinds";

export interface AssetContext {
  asset: AssetSummary;
  kind: AssetKind;
  /** The run whose attempt registered it (null: an import, or a run not in the inventory). */
  producer: WorkspaceRunRow | null;
  /** The producing run's input assets that are known. */
  inputs: AssetSummary[];
  /** Runs that name this asset in their inputs. */
  usedBy: WorkspaceRunRow[];
  imported: boolean;
}

export const isImported = (asset: AssetSummary): boolean =>
  asset.origin ? asset.origin.kind !== "execution" : false;

export const producerOf = (
  asset: AssetSummary,
  runs: readonly WorkspaceRunRow[],
): WorkspaceRunRow | null => {
  const runId = asset.origin?.runId;
  if (!runId) return null;
  return (
    runs.find(
      (run) => run.id === runId && (!asset.projectId || run.projectId === asset.projectId),
    ) ??
    runs.find((run) => run.id === runId) ??
    null
  );
};

export const usersOf = (assetId: string, runs: readonly WorkspaceRunRow[]): WorkspaceRunRow[] =>
  runs.filter((run) => run.inputs.includes(assetId));

export const assetContext = (
  asset: AssetSummary,
  assets: readonly AssetSummary[],
  runs: readonly WorkspaceRunRow[],
): AssetContext => {
  const producer = producerOf(asset, runs);
  const byId = new Map(assets.map((item) => [item.id, item]));
  return {
    asset,
    kind: kindOfAsset(asset),
    producer,
    inputs: (producer?.inputs ?? []).flatMap((id) => {
      const input = byId.get(id);
      return input ? [input] : [];
    }),
    usedBy: usersOf(asset.id, runs),
    imported: isImported(asset),
  };
};

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The host of an import URI, or the URI itself when it has none. */
export const importSource = (uri: string | null): string => {
  if (!uri) return "outside a run";
  try {
    return new URL(uri).host || uri;
  } catch {
    return uri;
  }
};

/** One sentence placing the asset: who made it, where, who uses it. */
export const contextSentence = (
  context: AssetContext,
  runName: (run: WorkspaceRunRow) => string,
  cited: number | null,
): string => {
  const { producer, usedBy, imported, asset, kind } = context;
  const parts: string[] = [];
  if (imported) parts.push(`Imported from ${importSource(asset.origin?.uri ?? null)}`);
  else if (producer)
    parts.push(
      `${KIND_NOUN[kind]} from ${runName(producer)} in ${producer.experimentName || producer.experimentId}`,
    );
  else if (asset.origin?.runId) parts.push(`${KIND_NOUN[kind]} from run ${asset.origin.runId}`);
  parts.push(usedBy.length ? `used by ${plural(usedBy.length, "run")}` : "not used yet");
  if (cited) parts.push(`cited in ${plural(cited, "document")}`);
  return parts.join(" · ");
};

const KIND_NOUN: Record<AssetKind, string> = {
  structure: "Structure",
  table: "Table",
  model: "Weights",
  image: "Image",
  text: "Text",
  data: "Data",
};

// ── landing: assets grouped by their context ─────────────────────────────

export type AssetGrouping = "experiment" | "project" | "kind" | "none";

export interface AssetBlock {
  key: string;
  /** The producing run, or null for imports (then `source` names where they came from). */
  run: WorkspaceRunRow | null;
  source: string | null;
  assets: AssetSummary[];
}

export interface AssetGroup {
  key: string;
  kind: "experiment" | "project" | "imported" | "asset-kind" | "unknown" | "all";
  title: string;
  /** A second, muted name: the experiment's project. */
  where: string | null;
  count: number;
  blocks: AssetBlock[];
}

const newestFirst = (left: AssetSummary, right: AssetSummary): number =>
  right.updatedAt.localeCompare(left.updatedAt);

/** Group assets under the run (or import source) they came from. */
const blocksOf = (
  assets: readonly AssetSummary[],
  runs: readonly WorkspaceRunRow[],
): AssetBlock[] => {
  const blocks = new Map<string, AssetBlock>();
  for (const asset of [...assets].sort(newestFirst)) {
    const run = isImported(asset) ? null : producerOf(asset, runs);
    const source = run ? null : (asset.origin?.uri ?? asset.origin?.runId ?? null);
    const key = run ? `run:${run.projectId}/${run.id}` : `src:${source ?? asset.id}`;
    const block = blocks.get(key) ?? { key, run, source, assets: [] };
    block.assets.push(asset);
    blocks.set(key, block);
  }
  return [...blocks.values()];
};

export const groupAssets = (
  assets: readonly AssetSummary[],
  runs: readonly WorkspaceRunRow[],
  grouping: AssetGrouping,
  projectName: (projectId: string) => string,
): AssetGroup[] => {
  if (grouping === "none") {
    const sorted = [...assets].sort(newestFirst);
    return [
      {
        key: "all",
        kind: "all",
        title: "All assets",
        where: null,
        count: sorted.length,
        blocks: [{ key: "all", run: null, source: null, assets: sorted }],
      },
    ];
  }
  if (grouping === "kind") {
    const byKind = new Map<AssetKind, AssetSummary[]>();
    for (const asset of assets) {
      const kind = kindOfAsset(asset);
      byKind.set(kind, [...(byKind.get(kind) ?? []), asset]);
    }
    return [...byKind.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([kind, rows]) => ({
        key: `kind:${kind}`,
        kind: "asset-kind",
        title: KIND_NOUN[kind],
        where: null,
        count: rows.length,
        blocks: blocksOf(rows, runs),
      }));
  }

  const groups = new Map<string, { group: AssetGroup; rows: AssetSummary[] }>();
  const add = (key: string, make: () => AssetGroup, asset: AssetSummary): void => {
    const entry = groups.get(key) ?? { group: make(), rows: [] };
    entry.rows.push(asset);
    groups.set(key, entry);
  };
  for (const asset of assets) {
    if (isImported(asset)) {
      add(
        "imported",
        () => ({
          key: "imported",
          kind: "imported",
          title: "Imported",
          where: null,
          count: 0,
          blocks: [],
        }),
        asset,
      );
      continue;
    }
    const run = producerOf(asset, runs);
    if (grouping === "project") {
      const projectId = run?.projectId ?? asset.projectId ?? "";
      add(
        `project:${projectId}`,
        () => ({
          key: `project:${projectId}`,
          kind: "project",
          title: run?.projectName || projectName(projectId),
          where: null,
          count: 0,
          blocks: [],
        }),
        asset,
      );
    } else if (run) {
      add(
        `experiment:${run.projectId}/${run.experimentId}`,
        () => ({
          key: `experiment:${run.projectId}/${run.experimentId}`,
          kind: "experiment",
          title: run.experimentName || run.experimentId,
          where: run.projectName || projectName(run.projectId),
          count: 0,
          blocks: [],
        }),
        asset,
      );
    } else {
      add(
        "unknown",
        () => ({
          key: "unknown",
          kind: "unknown",
          title: "Run not loaded",
          where: null,
          count: 0,
          blocks: [],
        }),
        asset,
      );
    }
  }
  const order = (group: AssetGroup): number =>
    group.kind === "imported" ? 2 : group.kind === "unknown" ? 1 : 0;
  return [...groups.values()]
    .map(({ group, rows }) => ({ ...group, count: rows.length, blocks: blocksOf(rows, runs) }))
    .sort(
      (left, right) =>
        order(left) - order(right) ||
        (right.blocks[0]?.assets[0]?.updatedAt ?? "").localeCompare(
          left.blocks[0]?.assets[0]?.updatedAt ?? "",
        ),
    );
};
