/**
 * Query-key factory for the TanStack Query server-state cache.
 *
 * Keys are hierarchical on purpose: invalidating a prefix drops everything
 * beneath it, so `qk.run(id)` covers logs / execution / files / assets /
 * metrics for that run, `["projects", pid]` covers a project's experiments and
 * their runs, and `["knowledge"]` covers list / note / backlinks / search.
 *
 * Keys are deliberately **not** prefixed by workspace — that would reintroduce
 * the serial "workspaces first" bootstrap dependency. A workspace switch
 * instead removes every key except `workspaces` / `targets` (see
 * `queryClient.ts`).
 *
 * Filter objects go in the last segment: TanStack hashes them
 * deterministically (key order does not matter).
 */

/** JSON-serializable filter/params segment. */
export type KeyParams = Readonly<Record<string, string | number | boolean | null | undefined>>;

/** Asset list scope — the workspace-wide list or one project's list. */
export type AssetScopeKey = { kind: "workspace" } | { kind: "project"; id: string };

/** Which byte window of a file a viewer holds. */
export type FileWindowKey = "full" | { tail: number } | { offset: number; length: number };

export const qk = {
  // ── cross-workspace (survive a workspace switch) ───────────────────────
  workspaces: () => ["workspaces"] as const,
  targets: () => ["targets"] as const,
  /** Remote-workspace registry — the list you may switch *to*. */
  workspaceTargets: () => ["workspace-targets"] as const,

  // ── workspace shell ───────────────────────────────────────────────────
  info: () => ["workspace", "info"] as const,
  tree: (path: string, depth: number) => ["tree", path, depth] as const,
  fileWindow: (path: string, win: FileWindowKey) => ["file", path, win] as const,

  // ── entity hierarchy ──────────────────────────────────────────────────
  projects: () => ["projects"] as const,
  projectsFor: (wsKey: string) => ["projects", "ws", wsKey] as const,
  experiments: (pid: string) => ["projects", pid, "experiments"] as const,
  experimentRuns: (pid: string, eid: string) =>
    ["projects", pid, "experiments", eid, "runs"] as const,

  // ── runs ──────────────────────────────────────────────────────────────
  runsIndex: (filter: KeyParams | null) => ["runs-index", filter] as const,
  run: (id: string) => ["run", id] as const,
  runLogs: (id: string, exec: string | null, tail: number) =>
    ["run", id, "logs", exec ?? "latest", tail] as const,
  runExecution: (id: string, exec: string | null) =>
    ["run", id, "execution", exec ?? "latest"] as const,
  runFiles: (id: string) => ["run", id, "files"] as const,
  runAssets: (id: string) => ["run", id, "assets"] as const,
  runMetrics: (id: string) => ["run", id, "metrics"] as const,
  runFileWindow: (id: string, path: string, win: FileWindowKey) =>
    ["run", id, "file", path, win] as const,

  // ── assets ────────────────────────────────────────────────────────────
  assets: (scope: AssetScopeKey) => ["assets", scope] as const,
  asset: (id: string) => ["asset", id] as const,
  assetLineage: (id: string) => ["asset", id, "lineage"] as const,
  assetContent: (id: string, win: FileWindowKey) => ["asset", id, "content", win] as const,

  // ── knowledge ─────────────────────────────────────────────────────────
  knowledge: (filter: KeyParams | null) => ["knowledge", "list", filter ?? null] as const,
  knowledgeNote: (path: string) => ["knowledge", "note", path] as const,
  knowledgeBacklinks: (path: string) => ["knowledge", "backlinks", path] as const,
  knowledgeSearch: (q: string) => ["knowledge", "search", q] as const,

  // ── events / agent / approvals ────────────────────────────────────────
  events: (params: KeyParams | null) => ["events", params ?? null] as const,
  agentSessions: () => ["agent", "sessions"] as const,
  agentSession: (id: string) => ["agent", "session", id] as const,
  agentHealth: () => ["agent", "health"] as const,
  agentProvider: () => ["agent", "provider"] as const,
  agentSkills: () => ["agent", "skills"] as const,
  knowledgeSources: () => ["agent", "knowledge-sources"] as const,
  plan: (pid: string, eid: string, rid: string) => ["plan", pid, eid, rid] as const,
  curateTask: (pid: string, eid: string, tid: string) => ["curate", pid, eid, tid] as const,
  approvals: () => ["approvals"] as const,
} as const;

export type QueryKeyFactory = typeof qk;
export type AnyQueryKey = ReturnType<QueryKeyFactory[keyof QueryKeyFactory]>;

/** Root segments that must survive a workspace switch. */
export const CROSS_WORKSPACE_ROOTS: ReadonlySet<unknown> = new Set([
  "workspaces",
  "targets",
  "workspace-targets",
]);

/** True when `candidate` starts with every segment of `prefix`. */
export const isKeyPrefix = (prefix: readonly unknown[], candidate: readonly unknown[]): boolean =>
  prefix.length <= candidate.length &&
  prefix.every((segment, index) => Object.is(segment, candidate[index]));
