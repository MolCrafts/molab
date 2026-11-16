/**
 * Reading an attempt's metrics in the browser.
 *
 * The server is a filesystem here, nothing more: it lists an attempt's files
 * and hands back their bytes. Which of those files is plottable, and what the
 * numbers in them mean, is decided entirely on this side — by whichever
 * reader the registry says claims the file. molrs reads solver logs in WASM,
 * so a chart comes straight from `log.lammps` with no server-side parsing and
 * no intermediate file.
 *
 * That split is the point: adding a format must never require a server
 * change, and the server must never learn a file layout.
 */

import { runsApi } from "@/api/runs";
import { resolveMetricReaderForPath, resolveMetricReaderForText } from "@/lib/contribution-runtime";
import type {
  MetricReaderContribution,
  MetricReadRequest,
  MetricRecordSample,
} from "@/lib/contribution-types";

/** Where an attempt lives, as the file API addresses it. */
export interface ExecutionCoords {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
  /**
   * Served workspace holding the run. Omitted means the active one — the
   * single-workspace path every existing caller is on. A comparison that spans
   * workspaces sets it, and the reads go to `/api/workspaces/{ws}/…` instead.
   */
  workspaceKey?: string;
}

/** One file a reader claimed, and what came out of it. */
export interface SourceRead {
  path: string;
  format: string;
  label: string;
  /** Size at read time — a tailable source re-reads when this changes. */
  revision: number;
  tailable: boolean;
  records: MetricRecordSample[];
  error?: string;
}

export interface MetricsRead {
  sources: SourceRead[];
  records: MetricRecordSample[];
}

interface FileNode {
  name?: string | null;
  relPath?: string | null;
  type?: string | null;
  size?: number | null;
  children?: FileNode[] | null;
}

/** Flatten the file tree; the API returns it nested. */
const flatten = (nodes: FileNode[] | null | undefined): FileNode[] => {
  const out: FileNode[] = [];
  for (const node of nodes ?? []) {
    if (node.type === "file") {
      out.push(node);
    }
    out.push(...flatten(node.children));
  }
  return out;
};

/** One of an attempt's directories, as the server declares it. */
export interface ExecutionDir {
  name: string;
  purpose: string;
  versioned: boolean;
  products: boolean;
}

/**
 * Rank a file by the directory it sits in.
 *
 * The server says which directories hold results and which are scratch; this
 * side never decides that from a name. Scratch sorts last rather than being
 * dropped — a run that wrote its only metrics there should still chart, just
 * behind anything promoted.
 */
const tierRank = (path: string, dirs: readonly ExecutionDir[]): number => {
  const head = path.replace(/\\/g, "/").split("/")[0];
  const index = dirs.findIndex((dir) => dir.name === head);
  if (index < 0) return dirs.length; // attempt root: after every declared tier
  return dirs[index].products ? index : dirs.length + 1;
};

/**
 * Files some reader claims by name, cheapest check first.
 *
 * Name-only on purpose: this decides what to *fetch*, and fetching every file
 * to ask its content would defeat the point. The reader's own content check
 * runs once the bytes arrive.
 *
 * Ordered by tier so a promoted product outranks the raw file it came from:
 * the same metrics WAL can exist in two directories, and the registered one
 * is the answer.
 */
export const claimableFiles = (
  nodes: FileNode[] | null | undefined,
  dirs: readonly ExecutionDir[] = [],
): { path: string; size: number; reader: MetricReaderContribution }[] => {
  const claimed: { path: string; size: number; reader: MetricReaderContribution }[] = [];
  for (const node of flatten(nodes)) {
    const path = node.relPath ?? node.name ?? "";
    if (!path) continue;
    const reader = resolveMetricReaderForPath(path);
    if (reader) {
      claimed.push({ path, size: node.size ?? 0, reader });
    }
  }
  if (dirs.length === 0) return claimed;
  return claimed
    .map((entry, index) => ({ entry, index, rank: tierRank(entry.path, dirs) }))
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .map(({ entry }) => entry);
};

/**
 * Read every plottable file in one attempt.
 *
 * A reader that throws — a missing WASM export, an unreadable file — costs
 * its own source and nothing else: one broken format must not blank a chart
 * that has other sources.
 */
export const readExecutionMetrics = async (
  coords: ExecutionCoords,
  request: MetricReadRequest = {},
): Promise<MetricsRead> => {
  const { projectId, experimentId, runId, executionId, workspaceKey } = coords;
  const files = workspaceKey
    ? await runsApi.getRunFilesWs(workspaceKey, projectId, experimentId, runId, executionId)
    : await runsApi.getRunFiles(projectId, experimentId, runId, executionId);
  const candidates = claimableFiles(
    files.nodes as FileNode[] | undefined,
    (files.dirs ?? []) as ExecutionDir[],
  );

  const sources: SourceRead[] = [];
  for (const candidate of candidates) {
    const base = {
      path: candidate.path,
      format: candidate.reader.format,
      label: candidate.reader.label,
      revision: candidate.size,
      tailable: candidate.reader.tailable ?? false,
    };
    try {
      const file = workspaceKey
        ? await runsApi.getRunFileTextWs(
            workspaceKey,
            projectId,
            experimentId,
            runId,
            executionId,
            candidate.path,
          )
        : await runsApi.getRunFileText(projectId, experimentId, runId, executionId, candidate.path);
      const text = file.content ?? "";
      // Name got us here; content decides. A `.out` that is a scheduler log
      // rather than a solver log drops out at this step.
      const reader = resolveMetricReaderForText(candidate.path, text);
      if (!reader) continue;
      const records = await reader.read(
        { path: candidate.path, text, revision: file.size ?? text.length },
        request,
      );
      sources.push({ ...base, format: reader.format, label: reader.label, records });
    } catch (readError) {
      sources.push({
        ...base,
        records: [],
        error: readError instanceof Error ? readError.message : String(readError),
      });
    }
  }

  return { sources, records: sources.flatMap((source) => source.records) };
};
