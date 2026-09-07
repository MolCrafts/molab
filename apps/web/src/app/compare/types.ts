/**
 * Identity for a run that is being compared against runs from elsewhere.
 *
 * A comparison set spans experiments, projects and served workspaces, so the
 * `(projectId, experimentId, runId)` triple every other API path uses is not
 * enough on its own — two workspaces can both hold a project called `peo-tg`.
 * `workspaceKey` is the served-set key from `GET /api/workspaces`; it is the
 * only level the backend does not stamp onto a run row, so the client adds it
 * at the point where it knows which workspace it asked.
 *
 * Everything here is an id, never a path. A workspace path is navigated by
 * people and every segment of it is a *name* — see the invariant in
 * `app/runs/types.ts` and `src/molexp/workspace/naming.py`.
 */

export interface RunRef {
  /** Served-workspace key (`GET /api/workspaces` → `key`). */
  workspaceKey: string;
  projectId: string;
  experimentId: string;
  runId: string;
}

/** Ordered levels of a ref, outermost first — the order ids are encoded in. */
const REF_FIELDS = ["workspaceKey", "projectId", "experimentId", "runId"] as const;

/**
 * Stable string form of a ref, for Set membership, localStorage and the URL.
 *
 * Segments are percent-encoded because a project or run id may legally contain
 * `/` in a hand-authored workspace, and the key is split back on `/`.
 */
export const refKey = (ref: RunRef): string =>
  REF_FIELDS.map((field) => encodeURIComponent(ref[field])).join("/");

/**
 * One run in the comparison set.
 *
 * Display names and `parameters` are denormalised from the run row at the
 * moment of adding, so the tray, the shortest-unique-label pass and the
 * "colour by <parameter>" picker all render without re-fetching anything. The
 * set is a selection, not a cache of run state — status is deliberately absent.
 */
export interface CompareEntry {
  ref: RunRef;
  /**
   * Whether this staged run is currently part of the comparison.
   *
   * The panel is a staging area, not the comparison itself: a run stays in it
   * while you toggle it in and out of the chart, so narrowing a set of twenty
   * to the three that matter does not mean losing the other seventeen and
   * re-gathering them from three different projects.
   */
  selected: boolean;
  /** Chosen attempt; null means "latest", resolved when metrics are scanned. */
  executionId: string | null;
  workspaceLabel: string;
  projectName: string;
  experimentName: string;
  runName: string;
  parameters: Record<string, unknown>;
  /** ISO-8601; orders the tray so the set reads in the order it was built. */
  addedAt: string;
}
