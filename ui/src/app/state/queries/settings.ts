/**
 * Settings / configuration queries.
 *
 * These are the last hand-rolled `useState` + `useEffect` loads in the app.
 * Unlike the run and knowledge migrations this one is about consistency rather
 * than latency — settings panels are one-shot loads behind user navigation, so
 * there was never a polling or waterfall problem to fix. Two things do improve:
 *
 * 1. **`GET /api/targets` is now fetched once.** {@link useTargetsQuery} already
 *    served the run and experiment dialogs; `ComputeTargetsPanel` was issuing
 *    the same request under its own `useState`. Both now share `qk.targets()`,
 *    so opening Settings after opening a dialog costs nothing.
 * 2. **`GET /api/agent/provider` is fetched once.** The model picker and three
 *    separate sections of the agent settings page each loaded it on mount.
 *    One key, one request, and a provider write updates all four.
 *
 * Config reads use a 5-minute `staleTime` (matching `targetsQuery`): this data
 * changes only when the operator changes it, and every mutation here
 * invalidates its own key, so staleness is bounded by the user's own actions
 * rather than by a timer.
 *
 * Agent-admin endpoints answer 503 when no provider is configured, which
 * `agentProbe` memoizes. These queries therefore set `retry: false` — retrying
 * a "not configured" answer buys nothing, and the shared `shouldRetry` would
 * otherwise treat 503 as a transient server error.
 */

import {
  queryOptions,
  type UseMutationResult,
  type UseQueryResult,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { WorkspaceTargetResponse } from "@/api/generated/models/WorkspaceTargetResponse";
import { WorkspaceService } from "@/api/generated/services/WorkspaceService";
import {
  type ApiAgentProvider,
  type ApiKnowledgeSources,
  type ApiSkill,
  agentAdminApi,
} from "@/app/state/api";
import { qk } from "./keys";

/** Operator configuration changes only when the operator changes it. */
export const CONFIG_STALE_MS = 5 * 60_000;

// ── remote workspace registry ───────────────────────────────────────────────

export const workspaceTargetsQuery = () =>
  queryOptions({
    queryKey: qk.workspaceTargets(),
    queryFn: async (): Promise<WorkspaceTargetResponse[]> => {
      const response = await WorkspaceService.listWorkspaceTargetsApiWorkspaceTargetsGet();
      return response.targets;
    },
    staleTime: CONFIG_STALE_MS,
  });

/**
 * Registered remote-workspace descriptors.
 *
 * Keyed cross-workspace on purpose: this is the list of workspaces you may
 * switch *to*, so switching must not evict it (see `CROSS_WORKSPACE_ROOTS`).
 */
export const useWorkspaceTargetsQuery = (): UseQueryResult<WorkspaceTargetResponse[]> =>
  useQuery(workspaceTargetsQuery());

// ── agent provider ──────────────────────────────────────────────────────────

export const agentProviderQuery = () =>
  queryOptions({
    queryKey: qk.agentProvider(),
    queryFn: (): Promise<ApiAgentProvider> => agentAdminApi.getProvider(),
    staleTime: CONFIG_STALE_MS,
    retry: false,
  });

/**
 * The configured agent provider (models, tiers, instructions, credentials).
 *
 * Shared by the composer's model picker and the agent settings sections, which
 * between them used to issue four independent requests for this one document.
 */
export const useAgentProviderQuery = (): UseQueryResult<ApiAgentProvider> =>
  useQuery(agentProviderQuery());

// ── skills ──────────────────────────────────────────────────────────────────

export const agentSkillsQuery = () =>
  queryOptions({
    queryKey: qk.agentSkills(),
    queryFn: (): Promise<ApiSkill[]> => agentAdminApi.listSkills(),
    staleTime: CONFIG_STALE_MS,
    retry: false,
  });

export const useAgentSkillsQuery = (
  options: { enabled?: boolean } = {},
): UseQueryResult<ApiSkill[]> =>
  useQuery({ ...agentSkillsQuery(), enabled: options.enabled ?? true });

// ── molmcp knowledge-source pin ─────────────────────────────────────────────

export const knowledgeSourcesQuery = () =>
  queryOptions({
    queryKey: qk.knowledgeSources(),
    queryFn: (): Promise<ApiKnowledgeSources> => agentAdminApi.getKnowledgeSources(),
    staleTime: CONFIG_STALE_MS,
    retry: false,
  });

export const useKnowledgeSourcesQuery = (): UseQueryResult<ApiKnowledgeSources> =>
  useQuery(knowledgeSourcesQuery());

// ── mutations ───────────────────────────────────────────────────────────────

/**
 * Persist the molmcp knowledge-source pin.
 *
 * The response *is* the new state, so it is written straight into the cache
 * rather than invalidated — the panel would otherwise flash the previous
 * selection while a refetch it already has the answer to comes back.
 */
export const useKnowledgeSourcesMutation = (): UseMutationResult<
  ApiKnowledgeSources,
  Error,
  string[]
> => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (sources: string[]) => agentAdminApi.updateKnowledgeSources(sources),
    onSuccess: (updated) => {
      client.setQueryData(qk.knowledgeSources(), updated);
    },
  });
};

/**
 * Write a provider document the server just returned into the cache.
 *
 * Provider writes echo the full new document, so refetching would ask for
 * something we already hold — and would flash the previous values while it
 * lands. Every reader of `qk.agentProvider()` updates at once.
 */
export const useApplyAgentProvider = (): ((provider: ApiAgentProvider) => void) => {
  const client = useQueryClient();
  return (provider: ApiAgentProvider) => {
    client.setQueryData(qk.agentProvider(), provider);
  };
};

/** Invalidate the skill list after a create / edit / delete. */
export const useInvalidateAgentSkills = (): (() => Promise<void>) => {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: qk.agentSkills() });
  };
};

/** Invalidate the compute-target list after an add / remove. */
export const useInvalidateTargets = (): (() => Promise<void>) => {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: qk.targets() });
  };
};

/** Invalidate the remote-workspace registry after an add / remove. */
export const useInvalidateWorkspaceTargets = (): (() => Promise<void>) => {
  const client = useQueryClient();
  return async () => {
    await client.invalidateQueries({ queryKey: qk.workspaceTargets() });
  };
};
