import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { knowledgeApi } from "@/api";
import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import {
  type KnowledgeListFilters,
  knowledgeBacklinksQueryOptions,
  knowledgeKeys,
  useKnowledgeListQuery,
} from "./queries";
/** Optional tag/status narrowing forwarded to `listKnowledge` (06 query support). */
export type KnowledgeDocFilters = KnowledgeListFilters;

/**
 * Shared query-cache facade for the Knowledge document tree. It loads Notes
 * through the canonical list query and exposes
 * imperative create / rename / move / delete verbs plus a backlinks lookup,
 * each routed through `knowledgeApi`. Successful mutations invalidate the
 * shared list keys so tree, viewer, controls, inspector, and palette realign.
 */
export interface UseKnowledgeDocs {
  notes: NoteSummary[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  createDoc: (name: string, parentPath?: string | null) => Promise<void>;
  renameDoc: (path: string, name: string) => Promise<void>;
  moveDoc: (path: string, parentPath: string) => Promise<void>;
  deleteDoc: (path: string) => Promise<void>;
  getBacklinks: (path: string) => Promise<NoteSummary[]>;
}

const toMessage = (err: unknown, fallback: string): string =>
  err instanceof Error ? err.message : fallback;

export const useKnowledgeDocs = (filters: KnowledgeDocFilters = {}): UseKnowledgeDocs => {
  const { tag = null, status = null } = filters;
  const queryClient = useQueryClient();
  const listQuery = useKnowledgeListQuery({ tag, status });

  const reload = useCallback(async (): Promise<void> => {
    await listQuery.refetch();
  }, [listQuery.refetch]);

  const invalidateLists = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: knowledgeKeys.lists() });
  }, [queryClient]);

  const createDoc = useCallback(
    async (name: string, parentPath?: string | null): Promise<void> => {
      await knowledgeApi.createDoc(name, { parentPath: parentPath ?? null });
      await invalidateLists();
    },
    [invalidateLists],
  );

  const renameDoc = useCallback(
    async (path: string, name: string): Promise<void> => {
      await knowledgeApi.renameDoc(path, name);
      await invalidateLists();
    },
    [invalidateLists],
  );

  const moveDoc = useCallback(
    async (path: string, parentPath: string): Promise<void> => {
      await knowledgeApi.moveDoc(path, parentPath);
      await invalidateLists();
    },
    [invalidateLists],
  );

  const deleteDoc = useCallback(
    async (path: string): Promise<void> => {
      await knowledgeApi.deleteDoc(path);
      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
    },
    [queryClient],
  );

  const getBacklinks = useCallback(
    async (path: string): Promise<NoteSummary[]> => {
      const response = await queryClient.fetchQuery(knowledgeBacklinksQueryOptions(path));
      return response.backlinks;
    },
    [queryClient],
  );

  return {
    notes: listQuery.data?.notes ?? [],
    loading: listQuery.isFetching,
    error: listQuery.error
      ? toMessage(listQuery.error, "Failed to load knowledge documents.")
      : null,
    reload,
    createDoc,
    renameDoc,
    moveDoc,
    deleteDoc,
    getBacklinks,
  };
};

/**
 * The universe of tag + status values across all notes (unfiltered), used to
 * populate the knowledge-tree filter. The unfiltered shared query keeps the
 * option list from collapsing when a filter is applied server-side.
 */
export interface UseKnowledgeFacets {
  tags: string[];
  statuses: string[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

export const useKnowledgeFacets = (): UseKnowledgeFacets => {
  const listQuery = useKnowledgeListQuery();

  const reload = useCallback(async (): Promise<void> => {
    await listQuery.refetch();
  }, [listQuery.refetch]);

  const notes = listQuery.data?.notes ?? [];

  const tags = useMemo(
    () => [...new Set(notes.flatMap((note) => note.tags ?? []))].sort(),
    [notes],
  );
  const statuses = useMemo(
    () =>
      [...new Set(notes.map((note) => note.status).filter((s): s is string => Boolean(s)))].sort(),
    [notes],
  );

  return {
    tags,
    statuses,
    loading: listQuery.isFetching,
    error: listQuery.error ? toMessage(listQuery.error, "Failed to load knowledge filters.") : null,
    reload,
  };
};
