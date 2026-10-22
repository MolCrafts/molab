/**
 * Identity for an item in the comparison bag, and for a run that is plotted.
 *
 * The bag spans experiments, projects and served workspaces, so a bare id is
 * not enough — two workspaces can both hold a project called `peo-tg`.
 * `workspaceKey` is the served-set key from `GET /api/workspaces`.
 *
 * Everything here is an id, never a path.
 */

/** Ordered levels of a run ref, outermost first — the order ids are encoded in. */
const RUN_REF_FIELDS = ["workspaceKey", "projectId", "experimentId", "runId"] as const;

export interface RunRef {
  /** Served-workspace key (`GET /api/workspaces` → `key`). */
  workspaceKey: string;
  projectId: string;
  experimentId: string;
  runId: string;
}

/**
 * Stable string form of a run ref, for Set membership, localStorage and the URL.
 *
 * Segments are percent-encoded because a project or run id may legally contain
 * `/` in a hand-authored workspace, and the key is split back on `/`.
 */
export const refKey = (ref: RunRef): string =>
  RUN_REF_FIELDS.map((field) => encodeURIComponent(ref[field])).join("/");

/**
 * One bag identity. Project and experiment omit the unused tail; every kind
 * still carries `workspaceKey`.
 */
export type CompareRef =
  | { kind: "project"; workspaceKey: string; projectId: string }
  | { kind: "experiment"; workspaceKey: string; projectId: string; experimentId: string }
  | {
      kind: "run";
      workspaceKey: string;
      projectId: string;
      experimentId: string;
      runId: string;
    };

const encodeSegment = (value: string): string => encodeURIComponent(value);

/** Percent-encoded key: 2 / 3 / 4 segments for project / experiment / run. */
export const itemKey = (ref: CompareRef): string => {
  switch (ref.kind) {
    case "project":
      return `${encodeSegment(ref.workspaceKey)}/${encodeSegment(ref.projectId)}`;
    case "experiment":
      return `${encodeSegment(ref.workspaceKey)}/${encodeSegment(ref.projectId)}/${encodeSegment(ref.experimentId)}`;
    case "run":
      return `${encodeSegment(ref.workspaceKey)}/${encodeSegment(ref.projectId)}/${encodeSegment(ref.experimentId)}/${encodeSegment(ref.runId)}`;
  }
};

export const parseItemKey = (key: string): CompareRef | null => {
  const parts = key.split("/").map((part) => {
    try {
      return decodeURIComponent(part);
    } catch {
      return null;
    }
  });
  if (parts.some((part) => part === null)) return null;
  const decoded = parts as string[];
  if (decoded.length === 2 && decoded[0] !== undefined && decoded[1] !== undefined) {
    return { kind: "project", workspaceKey: decoded[0], projectId: decoded[1] };
  }
  if (
    decoded.length === 3 &&
    decoded[0] !== undefined &&
    decoded[1] !== undefined &&
    decoded[2] !== undefined
  ) {
    return {
      kind: "experiment",
      workspaceKey: decoded[0],
      projectId: decoded[1],
      experimentId: decoded[2],
    };
  }
  if (
    decoded.length === 4 &&
    decoded[0] !== undefined &&
    decoded[1] !== undefined &&
    decoded[2] !== undefined &&
    decoded[3] !== undefined
  ) {
    return {
      kind: "run",
      workspaceKey: decoded[0],
      projectId: decoded[1],
      experimentId: decoded[2],
      runId: decoded[3],
    };
  }
  return null;
};

export const runRefFromCompare = (ref: Extract<CompareRef, { kind: "run" }>): RunRef => ({
  workspaceKey: ref.workspaceKey,
  projectId: ref.projectId,
  experimentId: ref.experimentId,
  runId: ref.runId,
});

/** True when `item` sits under `ancestor` in the Project → Experiment → Run tree. */
export const isDescendantRef = (item: CompareRef, ancestor: CompareRef): boolean => {
  if (item.workspaceKey !== ancestor.workspaceKey) return false;
  if (ancestor.kind === "run") return false;
  if (ancestor.kind === "project") {
    if (item.kind === "project") return false;
    return item.projectId === ancestor.projectId;
  }
  if (item.kind !== "run") return false;
  return item.projectId === ancestor.projectId && item.experimentId === ancestor.experimentId;
};

/**
 * One item in the comparison bag.
 *
 * Display names are denormalised at add time. The bag is a selection, not a
 * cache of run state — status is deliberately absent. `executionId` is only
 * meaningful on run-kind items.
 */
export interface CompareItem {
  ref: CompareRef;
  executionId: string | null;
  workspaceLabel: string;
  projectName: string;
  experimentName: string;
  runName: string;
  parameters: Record<string, unknown>;
  category: string | null;
  /** ISO-8601; orders the bag so the set reads in the order it was built. */
  addedAt: string;
}

/**
 * One run in the comparison matrix / chart.
 *
 * Produced by `expandToRuns`; never persisted. Identity is the four-tuple
 * `RunRef` so metrics caches stay keyed the way they were.
 */
export interface CompareEntry {
  ref: RunRef;
  /** Chosen attempt; null means "latest", resolved when metrics are scanned. */
  executionId: string | null;
  workspaceLabel: string;
  projectName: string;
  experimentName: string;
  runName: string;
  parameters: Record<string, unknown>;
  addedAt: string;
}

export const entryFromRunItem = (item: CompareItem): CompareEntry | null => {
  if (item.ref.kind !== "run") return null;
  return {
    ref: runRefFromCompare(item.ref),
    executionId: item.executionId,
    workspaceLabel: item.workspaceLabel,
    projectName: item.projectName,
    experimentName: item.experimentName,
    runName: item.runName,
    parameters: item.parameters,
    addedAt: item.addedAt,
  };
};
