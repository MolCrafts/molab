import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import {
  type KnowledgeFacets,
  knowledgeErrorMessage,
  useKnowledgeBacklinksFetcher,
  useKnowledgeFacetsQuery,
  useKnowledgeMutations,
  useKnowledgeNotesQuery,
} from "@/app/state/queries";

/** Optional tag/status narrowing applied to the shared note list. */
export interface KnowledgeDocFilters {
  tag?: string | null;
  status?: string | null;
}

/**
 * Data + mutation hook for the Knowledge document tree.
 *
 * A thin adapter over the shared TanStack Query layer
 * (`@/app/state/queries/knowledge`): the note list comes from the one
 * `GET /api/knowledge` cache entry — narrowed to `filters` by a client-side
 * `select`, so the doc tree, its facet filter, the command palette and the
 * knowledge viewer all share a single request — and each write verb invalidates
 * only the `["knowledge"]` keys, never a whole-workspace refresh.
 *
 * The interface is unchanged from the hand-rolled `useState` + `useEffect`
 * version it replaced, so every call site kept compiling.
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

export const useKnowledgeDocs = (filters: KnowledgeDocFilters = {}): UseKnowledgeDocs => {
  const { tag = null, status = null } = filters;
  const query = useKnowledgeNotesQuery({ tag, status });
  const { createDoc, renameDoc, moveDoc, deleteDoc } = useKnowledgeMutations();
  const getBacklinks = useKnowledgeBacklinksFetcher();

  return {
    notes: query.data ?? [],
    // `isFetching` (not `isPending`) so a background revalidation still shows
    // the tree's "Refreshing…" affordance, matching the old reload semantics.
    loading: query.isFetching,
    error: query.error
      ? knowledgeErrorMessage(query.error, "Failed to load knowledge documents.")
      : null,
    reload: async () => {
      await query.refetch();
    },
    createDoc,
    renameDoc,
    moveDoc,
    deleteDoc,
    getBacklinks,
  };
};

/**
 * The universe of tag + status values across all notes (unfiltered), used to
 * populate the knowledge-tree filter. Reads the same shared list cache entry as
 * {@link useKnowledgeDocs} through a `select`, so the option list never
 * collapses when a filter is applied — and costs no extra request.
 */
export interface UseKnowledgeFacets extends KnowledgeFacets {
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

export const useKnowledgeFacets = (): UseKnowledgeFacets => {
  const query = useKnowledgeFacetsQuery();
  return {
    tags: query.data?.tags ?? [],
    statuses: query.data?.statuses ?? [],
    loading: query.isFetching,
    error: query.error
      ? knowledgeErrorMessage(query.error, "Failed to load knowledge filters.")
      : null,
    reload: async () => {
      await query.refetch();
    },
  };
};
