/**
 * The single invalidation map: mutation kind / server change → query keys.
 *
 * Two entry points share it:
 *  - `invalidationsFor(change)` — pure; used by the SSE change stream.
 *  - `createInvalidators(client)` / `useInvalidate()` — the bound helpers that
 *    replace the 27 `onRefresh()` call sites (plan P2 §2b).
 *
 * Nothing here ever clears data: invalidation marks queries stale so the next
 * mount (or an active observer) refetches, while the current data keeps
 * rendering. `remove` is reserved for entities that no longer exist.
 */

import { type Query, type QueryClient, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import type { LeftPanelView } from "@/app/types";
import { CROSS_WORKSPACE_ROOTS, qk } from "./keys";

export type WorkspaceChangeKind =
  | "run"
  | "asset"
  | "knowledge"
  | "project"
  | "experiment"
  | "workspace"
  | "agent"
  | "approval"
  | "all";

/** One server-side change, as delivered by `GET /api/workspace/events/stream`. */
export interface WorkspaceChange {
  kind: WorkspaceChangeKind;
  ref: string | null;
  seq: number | null;
  projectId?: string;
  experimentId?: string;
  /** For `asset` changes scoped to a run. */
  runId?: string;
}

export type RefetchType = "active" | "inactive" | "all" | "none";

export interface InvalidationSpec {
  queryKey?: readonly unknown[];
  /** Match only this exact key (default: prefix match). */
  exact?: boolean;
  predicate?: (query: Query) => boolean;
  /** Remove instead of invalidate — for entities that no longer exist. */
  remove?: boolean;
}

const prefix = (queryKey: readonly unknown[]): InvalidationSpec => ({ queryKey });
const exact = (queryKey: readonly unknown[]): InvalidationSpec => ({ queryKey, exact: true });
const remove = (queryKey: readonly unknown[]): InvalidationSpec => ({ queryKey, remove: true });

const ROOT_TREE = exact(qk.tree("", 2));

/** Everything except the cross-workspace keys — the workspace-switch reset. */
export const notCrossWorkspace = (query: Query): boolean =>
  !CROSS_WORKSPACE_ROOTS.has(query.queryKey[0]);

/** Any experiment-runs list (`["projects", pid, "experiments", eid, "runs"]`). */
const anyExperimentRuns = (query: Query): boolean => {
  const key = query.queryKey;
  return key[0] === "projects" && key.length === 5 && key[4] === "runs";
};

/** Workspace-relative parent directory ("" for the root). */
export const parentDirOf = (path: string): string => {
  const trimmed = path.replace(/\/+$/, "");
  const slash = trimmed.lastIndexOf("/");
  return slash < 0 ? "" : trimmed.slice(0, slash);
};

/** The list-level keys to drop when the change stream cannot replay a gap. */
export const LIST_LEVEL_INVALIDATIONS: readonly InvalidationSpec[] = [
  exact(qk.info()),
  exact(qk.projects()),
  prefix(["runs-index"]),
  prefix(["assets"]),
  prefix(["knowledge"]),
  exact(qk.agentSessions()),
  exact(qk.approvals()),
  prefix(["events"]),
];

/** Pure map: one server change → the queries it makes stale. */
export function invalidationsFor(change: WorkspaceChange): InvalidationSpec[] {
  const { kind, ref, projectId, experimentId, runId } = change;
  switch (kind) {
    case "run": {
      const specs: InvalidationSpec[] = [];
      if (ref) specs.push(prefix(qk.run(ref)));
      if (projectId && experimentId) specs.push(exact(qk.experimentRuns(projectId, experimentId)));
      else specs.push({ predicate: anyExperimentRuns });
      specs.push(prefix(["runs-index"]), prefix(["events"]));
      return specs;
    }
    case "asset": {
      const specs: InvalidationSpec[] = [prefix(["assets"])];
      if (ref) specs.push(prefix(qk.asset(ref)));
      if (runId) specs.push(exact(qk.runAssets(runId)), exact(qk.runFiles(runId)));
      specs.push(prefix(["tree"]));
      return specs;
    }
    case "knowledge":
      return [prefix(["knowledge"])];
    case "project": {
      const specs: InvalidationSpec[] = [exact(qk.projects()), prefix(["projects", "ws"])];
      if (ref) specs.push(prefix(["projects", ref]));
      specs.push(ROOT_TREE);
      return specs;
    }
    case "experiment": {
      const specs: InvalidationSpec[] = [];
      if (projectId) {
        specs.push(exact(qk.experiments(projectId)));
        if (ref) specs.push(exact(qk.experimentRuns(projectId, ref)));
      }
      specs.push(exact(qk.projects()), ROOT_TREE);
      return specs;
    }
    case "workspace": {
      const specs: InvalidationSpec[] = [exact(qk.info())];
      if (ref) specs.push(exact(qk.tree(parentDirOf(ref), 1)), prefix(["file", ref]));
      else specs.push(prefix(["tree"]));
      return specs;
    }
    case "agent": {
      const specs: InvalidationSpec[] = [exact(qk.agentSessions())];
      if (ref) specs.push(exact(qk.agentSession(ref)));
      return specs;
    }
    case "approval":
      return [exact(qk.approvals())];
    case "all":
      return [{ predicate: notCrossWorkspace }];
  }
}

/** Apply specs to a client. `refetchType: "none"` only marks stale (hidden tabs). */
export async function applyInvalidations(
  client: QueryClient,
  specs: readonly InvalidationSpec[],
  options: { refetchType?: RefetchType } = {},
): Promise<void> {
  const refetchType = options.refetchType ?? "active";
  const pending: Promise<void>[] = [];
  for (const spec of specs) {
    const filters = {
      queryKey: spec.queryKey as readonly unknown[] | undefined,
      exact: spec.exact,
      predicate: spec.predicate,
    };
    if (spec.remove) client.removeQueries(filters);
    else pending.push(client.invalidateQueries({ ...filters, refetchType }));
  }
  await Promise.all(pending);
}

/** Bound helpers — one per mutation kind in the plan's `onRefresh()` table. */
export interface Invalidators {
  afterRunVerb: (ids: {
    runId: string;
    projectId?: string;
    experimentId?: string;
  }) => Promise<void>;
  afterRunCreate: (ids: { projectId: string; experimentId: string }) => Promise<void>;
  afterExperimentCreate: (ids: { projectId: string }) => Promise<void>;
  afterExperimentDelete: (ids: { projectId: string; experimentId: string }) => Promise<void>;
  afterProjectDelete: (ids: { projectId: string }) => Promise<void>;
  afterHarvest: (ids: { runId: string }) => Promise<void>;
  afterCurate: (ids: { projectId: string }) => Promise<void>;
  afterNoteMutation: (path?: string | null) => Promise<void>;
  afterAgentCreate: () => Promise<void>;
  afterAgentCancel: (sessionId: string) => Promise<void>;
  afterAgentMessage: (sessionId: string) => Promise<void>;
  afterAgentDelete: (sessionId: string) => Promise<void>;
  afterPlanDecision: (ids: {
    sessionId: string;
    plan?: { projectId: string; experimentId: string; runId: string };
  }) => Promise<void>;
  afterFsWrite: (path: string) => Promise<void>;
  afterWorkspaceSwitch: () => Promise<void>;
  /** The manual "refresh" affordance for one navigator view (active queries only). */
  invalidateView: (view: LeftPanelView) => Promise<void>;
  /** Escape hatch: apply raw specs. */
  apply: (
    specs: readonly InvalidationSpec[],
    options?: { refetchType?: RefetchType },
  ) => Promise<void>;
}

/** Keys the manual refresh of a navigator view touches. */
export function viewInvalidations(view: LeftPanelView): InvalidationSpec[] {
  switch (view) {
    case "runs":
      return [prefix(["runs-index"]), prefix(["events"])];
    case "projects":
    case "workflow":
      return [prefix(["projects"])];
    case "workspace":
      return [exact(qk.info()), prefix(["tree"])];
    case "asset":
      return [prefix(["assets"]), prefix(["asset"])];
    case "knowledge":
      return [prefix(["knowledge"])];
    case "agent":
      return [prefix(["agent"]), exact(qk.approvals())];
    case "settings":
      return [exact(qk.targets())];
  }
}

export function createInvalidators(client: QueryClient): Invalidators {
  const apply = (specs: readonly InvalidationSpec[], options?: { refetchType?: RefetchType }) =>
    applyInvalidations(client, specs, options);
  return {
    apply,
    afterRunVerb: ({ runId, projectId, experimentId }) =>
      apply([
        prefix(qk.run(runId)),
        projectId && experimentId
          ? exact(qk.experimentRuns(projectId, experimentId))
          : { predicate: anyExperimentRuns },
        prefix(["runs-index"]),
        prefix(["events"]),
      ]),
    afterRunCreate: ({ projectId, experimentId }) =>
      apply([
        exact(qk.experimentRuns(projectId, experimentId)),
        exact(qk.experiments(projectId)),
        prefix(["runs-index"]),
      ]),
    afterExperimentCreate: ({ projectId }) =>
      apply([exact(qk.experiments(projectId)), exact(qk.projects()), ROOT_TREE]),
    afterExperimentDelete: ({ projectId, experimentId }) =>
      apply([
        remove(qk.experimentRuns(projectId, experimentId)),
        exact(qk.experiments(projectId)),
        exact(qk.projects()),
        prefix(["runs-index"]),
        prefix(["assets"]),
        ROOT_TREE,
      ]),
    afterProjectDelete: ({ projectId }) =>
      apply([
        remove(["projects", projectId]),
        exact(qk.projects()),
        prefix(["projects", "ws"]),
        prefix(["runs-index"]),
        prefix(["assets"]),
        ROOT_TREE,
      ]),
    afterHarvest: ({ runId }) => apply([prefix(["knowledge"]), prefix(qk.run(runId))]),
    afterCurate: ({ projectId }) =>
      apply([
        prefix(["projects", projectId]),
        prefix(["assets"]),
        prefix(["tree"]),
        prefix(["knowledge"]),
        prefix(["runs-index"]),
      ]),
    afterNoteMutation: () => apply([prefix(["knowledge"])]),
    afterAgentCreate: () => apply([exact(qk.agentSessions())]),
    afterAgentCancel: (sessionId) =>
      apply([exact(qk.agentSession(sessionId)), exact(qk.agentSessions())]),
    afterAgentMessage: (sessionId) => apply([exact(qk.agentSession(sessionId))]),
    afterAgentDelete: (sessionId) =>
      apply([exact(qk.agentSessions()), remove(qk.agentSession(sessionId))]),
    afterPlanDecision: ({ sessionId, plan }) =>
      apply([
        exact(qk.agentSession(sessionId)),
        plan ? exact(qk.plan(plan.projectId, plan.experimentId, plan.runId)) : prefix(["plan"]),
        exact(qk.approvals()),
      ]),
    afterFsWrite: (path) => {
      const parent = parentDirOf(path);
      const specs: InvalidationSpec[] = [exact(qk.tree(parent, 1))];
      if (parent === "") specs.push(ROOT_TREE);
      return apply(specs);
    },
    afterWorkspaceSwitch: async () => {
      await client.cancelQueries({ predicate: notCrossWorkspace });
      client.removeQueries({ predicate: notCrossWorkspace });
    },
    invalidateView: (view) => apply(viewInvalidations(view), { refetchType: "active" }),
  };
}

/** React binding of {@link createInvalidators} for the provider's client. */
export function useInvalidate(): Invalidators {
  const client = useQueryClient();
  return useMemo(() => createInvalidators(client), [client]);
}
