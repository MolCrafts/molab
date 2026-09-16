/**
 * Server-state cache foundation (plan P2 §2a).
 *
 * - `queryClient` / `QueryProvider` — the one client and its provider.
 * - `qk` — the hierarchical query-key factory.
 * - `invalidationsFor` / `useInvalidate` — the single invalidation map.
 * - `fetchJsonConditional` — ETag/304-aware fetch for raw-`fetch` endpoints.
 * - `usePrefetchOnIntent` — hover/focus prefetch handlers.
 * - `useWorkspaceChangeStream` / `useFallbackInterval` — SSE-driven freshness.
 */

export {
  ACTIVITY_FALLBACK_POLL_MS,
  AGENT_HEALTH_STALE_MS,
  AGENT_SESSION_POLL_MS,
  APPROVALS_STALE_MS,
  agentSessionRefetchInterval,
  CURATE_POLL_MS,
  curateRefetchInterval,
  getApprovalsStreamErrored,
  isLiveAgentStatus,
  LIVE_AGENT_STATUSES,
  PLAN_DECISION_GRACE_MS,
  PLAN_POLL_MS,
  type PlanRefLike,
  planRefetchInterval,
  resetApprovalsStream,
  useAgentHealthQuery,
  useAgentSessionQuery,
  useApprovalsQuery,
  useApprovalsStream,
  useCurateTaskQuery,
  usePlanQuery,
  useWorkspaceEventsQuery,
} from "./agent";
export {
  acquireChangeStream,
  type ChangeStreamState,
  coalesce,
  startChangeStream,
  useChangeStreamState,
  useFallbackInterval,
  useWorkspaceChangeStream,
} from "./changeStream";
export {
  fetchJsonConditional,
  getStoredEtag,
  HttpStatusError,
  resetEtagCache,
} from "./etagFetch";
export {
  applyInvalidations,
  createInvalidators,
  type InvalidationSpec,
  type Invalidators,
  invalidationsFor,
  useInvalidate,
  viewInvalidations,
  type WorkspaceChange,
  type WorkspaceChangeKind,
} from "./invalidation";
export {
  type AssetScopeKey,
  type FileWindowKey,
  isKeyPrefix,
  type KeyParams,
  qk,
} from "./keys";
export {
  KNOWLEDGE_DETAIL_STALE_MS,
  KNOWLEDGE_LIST_STALE_MS,
  KNOWLEDGE_SEARCH_DEBOUNCE_MS,
  type KnowledgeFacets,
  type KnowledgeMutations,
  knowledgeErrorMessage,
  knowledgeQueries,
  prefetchKnowledgeNote,
  selectFacets,
  selectFiltered,
  selectIsNotePath,
  useDebouncedValue,
  useKnowledgeBacklinksFetcher,
  useKnowledgeBacklinksQuery,
  useKnowledgeFacetsQuery,
  useKnowledgeListQuery,
  useKnowledgeMutations,
  useKnowledgeNotePrefetch,
  useKnowledgeNoteQuery,
  useKnowledgeNotesQuery,
  useKnowledgeSearchQuery,
} from "./knowledge";
export { usePrefetchOnIntent } from "./prefetch";
export { QueryProvider } from "./QueryProvider";
export {
  createQueryClient,
  GC_TIME_MS,
  queryClient,
  resetForWorkspaceSwitch,
  STALE_TIME_MS,
  shouldRetry,
} from "./queryClient";
export {
  DEFAULT_LOG_TAIL,
  EMPTY_RUN_STATS,
  EMPTY_RUNS_INDEX,
  RUN_EXECUTION_POLL_MS,
  RUN_LOGS_POLL_MS,
  RUN_METRICS_POLL_MS,
  RUNS_FALLBACK_POLL_MS,
  RUNS_INDEX_LIMIT,
  RUNS_INDEX_STALE_MS,
  type RunLogsCoords,
  type RunMetricsPage,
  type RunsIndexView,
  runsIndexKey,
  usePrefetchRunRow,
  useRunAssetsQuery,
  useRunCoords,
  useRunExecutionQuery,
  useRunFilesQuery,
  useRunLogsQuery,
  useRunMetricsQuery,
  useRunRowPrefetch,
  useRunsIndexQuery,
} from "./runs";
export {
  agentProviderQuery,
  agentSkillsQuery,
  CONFIG_STALE_MS,
  knowledgeSourcesQuery,
  useAgentProviderQuery,
  useAgentSkillsQuery,
  useApplyAgentProvider,
  useInvalidateAgentSkills,
  useInvalidateTargets,
  useInvalidateWorkspaceTargets,
  useKnowledgeSourcesMutation,
  useKnowledgeSourcesQuery,
  useWorkspaceTargetsQuery,
  workspaceTargetsQuery,
} from "./settings";
export {
  EMPTY_SLICE_ERRORS,
  type ExpansionSets,
  expKey,
  parseExpKey,
  type SliceErrors,
  useWorkspaceSnapshot,
  type WorkspaceSnapshotResult,
} from "./snapshot";
export { useVisibleInterval } from "./useVisibleInterval";
export {
  agentSessionsQuery,
  assetsQuery,
  type ExperimentsSlice,
  experimentRunsQuery,
  experimentsQuery,
  prefetchExperimentRuns,
  prefetchExperiments,
  prefetchTreeChildren,
  projectsForQuery,
  projectsQuery,
  targetsQuery,
  treeChildrenQuery,
  treeQuery,
  useAgentSessionsQuery,
  useAssetsQuery,
  useExperimentQuery,
  useExperimentsQuery,
  useProjectAssetsQuery,
  useProjectAssetsRawQuery,
  useProjectsQuery,
  useTargetsQuery,
  useWorkspaceInfoQuery,
  useWorkspacesQuery,
  type WorkspaceInfo,
  workspaceInfoQuery,
  workspaceRootQuery,
  workspacesQuery,
} from "./workspace";
