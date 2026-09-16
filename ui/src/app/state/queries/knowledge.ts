/**
 * Knowledge-tab server state (plan P2 §2c).
 *
 * **One list request, four consumers.** `GET /api/knowledge` is fetched once
 * under the single key `qk.knowledge(null)` — always unfiltered — and the doc
 * tree, its facet filter, the global command palette and the knowledge viewer
 * all read that one cache entry through a `select`. Tag/status narrowing is a
 * client-side projection, not a second request: the server list is small, the
 * facet universe must not collapse when a filter is applied, and filtering in
 * `select` keeps the four consumers on one key.
 *
 * Note bodies and backlinks are their own keys so the viewer and the inspector
 * share one `getNote` round-trip instead of issuing two. Search is debounced by
 * the caller and keeps the previous hits while the next query is in flight.
 *
 * Every mutation invalidates the `["knowledge"]` prefix (list + note +
 * backlinks + search) and nothing else — never a whole-workspace refresh.
 */

import {
  keepPreviousData,
  type QueryClient,
  type UseQueryResult,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { BacklinksResponse } from "@/api/generated/models/BacklinksResponse";
import type { KnowledgeListResponse } from "@/api/generated/models/KnowledgeListResponse";
import type { KnowledgeSearchResponse } from "@/api/generated/models/KnowledgeSearchResponse";
import type { NoteDetailResponse } from "@/api/generated/models/NoteDetailResponse";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import { workspaceApi } from "@/app/state/api";
import { useInvalidate } from "./invalidation";
import { qk } from "./keys";
import { type PrefetchIntentHandlers, usePrefetchOnIntent } from "./prefetch";

/** The note/reference list changes only through this app's own mutations. */
export const KNOWLEDGE_LIST_STALE_MS = 60_000;
/** Bodies and backlinks follow edits more closely than the list does. */
export const KNOWLEDGE_DETAIL_STALE_MS = 30_000;
/** Keystroke settle time before a search query is issued. */
export const KNOWLEDGE_SEARCH_DEBOUNCE_MS = 300;

/** Render a thrown value as a message for a `WorkbenchOperationState`. */
export const knowledgeErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : error ? String(error) : fallback;

/**
 * The query-options factory every knowledge hook is built from.
 *
 * Exported so the options can be observed directly (tests, imperative
 * `fetchQuery` / `prefetchQuery`) — and so there is exactly one place where a
 * key is paired with its fetcher, which is what keeps the four list consumers
 * on one request.
 */
export const knowledgeQueries = {
  list: () => ({
    queryKey: qk.knowledge(null),
    queryFn: (): Promise<KnowledgeListResponse> => workspaceApi.listKnowledge(),
    staleTime: KNOWLEDGE_LIST_STALE_MS,
  }),
  note: (path: string) => ({
    queryKey: qk.knowledgeNote(path),
    queryFn: (): Promise<NoteDetailResponse> => workspaceApi.getNote(path),
    staleTime: KNOWLEDGE_DETAIL_STALE_MS,
  }),
  backlinks: (path: string) => ({
    queryKey: qk.knowledgeBacklinks(path),
    queryFn: async (): Promise<NoteSummary[]> => {
      const response: BacklinksResponse = await workspaceApi.getKnowledgeBacklinks(path);
      return response.backlinks;
    },
    staleTime: KNOWLEDGE_DETAIL_STALE_MS,
  }),
  search: (query: string) => ({
    queryKey: qk.knowledgeSearch(query),
    queryFn: (): Promise<KnowledgeSearchResponse> => workspaceApi.searchKnowledge(query),
    staleTime: KNOWLEDGE_DETAIL_STALE_MS,
    placeholderData: keepPreviousData,
  }),
} as const;

const listOptions = knowledgeQueries.list;
const noteOptions = knowledgeQueries.note;
const backlinksOptions = knowledgeQueries.backlinks;
const searchOptions = knowledgeQueries.search;

// ── selects (pure projections over the one list response) ──────────────────

/** Tag/status narrowing, AND semantics — the client-side twin of `?tag=&status=`. */
export const selectFiltered =
  (tag: string | null, status: string | null) =>
  (data: KnowledgeListResponse): NoteSummary[] => {
    if (tag === null && status === null) return data.notes;
    return data.notes.filter(
      (note) =>
        (tag === null || (note.tags ?? []).includes(tag)) &&
        (status === null || note.status === status),
    );
  };

export interface KnowledgeFacets {
  tags: string[];
  statuses: string[];
}

/**
 * The universe of tag + status values across **all** notes. Derived from the
 * unfiltered list so the facet options never collapse to the current filter.
 */
export const selectFacets = (data: KnowledgeListResponse): KnowledgeFacets => ({
  tags: [...new Set(data.notes.flatMap((note) => note.tags ?? []))].sort(),
  statuses: [
    ...new Set(data.notes.map((note) => note.status).filter((s): s is string => Boolean(s))),
  ].sort(),
});

/** True when `path` names a Note (rather than a literature Reference). */
export const selectIsNotePath =
  (path: string) =>
  (data: KnowledgeListResponse): boolean =>
    data.notes.some((note) => note.relPath === path);

// ── queries ────────────────────────────────────────────────────────────────

/** The whole knowledge list — notes + references. One key for every consumer. */
export function useKnowledgeListQuery(): UseQueryResult<KnowledgeListResponse, Error> {
  return useQuery(listOptions());
}

/** The note list, narrowed client-side by tag/status. Shares the list request. */
export function useKnowledgeNotesQuery(
  filters: { tag?: string | null; status?: string | null } = {},
): UseQueryResult<NoteSummary[], Error> {
  const { tag = null, status = null } = filters;
  // Memoized so the projection re-runs on a filter change, not on every render.
  const select = useMemo(() => selectFiltered(tag, status), [tag, status]);
  return useQuery({ ...listOptions(), select });
}

/** The facet universe for the knowledge filter. Shares the list request. */
export function useKnowledgeFacetsQuery(): UseQueryResult<KnowledgeFacets, Error> {
  return useQuery({ ...listOptions(), select: selectFacets });
}

/** A note's body, links and entity cards. */
export function useKnowledgeNoteQuery(
  path: string | null | undefined,
  options: { enabled?: boolean } = {},
): UseQueryResult<NoteDetailResponse, Error> {
  const relPath = path ?? "";
  return useQuery({
    ...noteOptions(relPath),
    enabled: relPath.length > 0 && (options.enabled ?? true),
  });
}

/** Every Concept linking at `path`. */
export function useKnowledgeBacklinksQuery(
  path: string | null | undefined,
  options: { enabled?: boolean } = {},
): UseQueryResult<NoteSummary[], Error> {
  const relPath = path ?? "";
  return useQuery({
    ...backlinksOptions(relPath),
    enabled: relPath.length > 0 && (options.enabled ?? true),
  });
}

/**
 * Body-aware search. Pass an already-debounced query; an empty one is disabled
 * (no request) and `keepPreviousData` holds the last hits while the next query
 * resolves, so the result list never blinks between keystrokes.
 */
export function useKnowledgeSearchQuery(
  query: string,
): UseQueryResult<KnowledgeSearchResponse, Error> {
  const trimmed = query.trim();
  return useQuery({ ...searchOptions(trimmed), enabled: trimmed.length > 0 });
}

// ── prefetch ───────────────────────────────────────────────────────────────

/** Warm a note's body so clicking a row paints from cache. */
export function prefetchKnowledgeNote(client: QueryClient, path: string): Promise<void> {
  return client.prefetchQuery(noteOptions(path));
}

/**
 * Hover/focus handlers that prefetch one note's body. A null/empty `path` (a
 * reference or entity row, which has no note body) yields inert handlers.
 */
export function useKnowledgeNotePrefetch(path: string | null | undefined): PrefetchIntentHandlers {
  const client = useQueryClient();
  return usePrefetchOnIntent(
    useCallback(() => (path ? prefetchKnowledgeNote(client, path) : undefined), [client, path]),
  );
}

// ── mutations ──────────────────────────────────────────────────────────────

export interface KnowledgeMutations {
  createDoc: (name: string, parentPath?: string | null) => Promise<void>;
  renameDoc: (path: string, name: string) => Promise<void>;
  moveDoc: (path: string, parentPath: string) => Promise<void>;
  deleteDoc: (path: string) => Promise<void>;
  /** True while any knowledge write is in flight. */
  isMutating: boolean;
}

/**
 * The knowledge write verbs. Each awaits its targeted invalidation, so a caller
 * that reports success is reporting it against a realigned cache.
 */
export function useKnowledgeMutations(): KnowledgeMutations {
  const { afterNoteMutation } = useInvalidate();

  const create = useMutation({
    mutationFn: ({ name, parentPath }: { name: string; parentPath?: string | null }) =>
      workspaceApi.createKnowledgeDoc(name, { parentPath: parentPath ?? null }),
    onSuccess: (note) => afterNoteMutation(note.relPath),
  });
  const rename = useMutation({
    mutationFn: ({ path, name }: { path: string; name: string }) =>
      workspaceApi.renameKnowledgeDoc(path, name),
    onSuccess: (_note, { path }) => afterNoteMutation(path),
  });
  const move = useMutation({
    mutationFn: ({ path, parentPath }: { path: string; parentPath: string }) =>
      workspaceApi.moveKnowledgeDoc(path, parentPath),
    onSuccess: (_note, { path }) => afterNoteMutation(path),
  });
  const remove = useMutation({
    mutationFn: (path: string) => workspaceApi.deleteKnowledgeDoc(path),
    onSuccess: (_void, path) => afterNoteMutation(path),
  });

  const isMutating = create.isPending || rename.isPending || move.isPending || remove.isPending;

  return useMemo(
    () => ({
      createDoc: async (name, parentPath) => {
        await create.mutateAsync({ name, parentPath });
      },
      renameDoc: async (path, name) => {
        await rename.mutateAsync({ path, name });
      },
      moveDoc: async (path, parentPath) => {
        await move.mutateAsync({ path, parentPath });
      },
      deleteDoc: async (path) => {
        await remove.mutateAsync(path);
      },
      isMutating,
    }),
    [create.mutateAsync, rename.mutateAsync, move.mutateAsync, remove.mutateAsync, isMutating],
  );
}

/** Imperative backlinks read that still populates (and reuses) the cache. */
export function useKnowledgeBacklinksFetcher(): (path: string) => Promise<NoteSummary[]> {
  const client = useQueryClient();
  return useCallback((path: string) => client.fetchQuery(backlinksOptions(path)), [client]);
}

// ── misc ───────────────────────────────────────────────────────────────────

/**
 * `value` delayed by `delayMs` of quiet. Used to keep search keystrokes out of
 * the query key until the user stops typing.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(handle);
  }, [value, delayMs]);
  return debounced;
}
