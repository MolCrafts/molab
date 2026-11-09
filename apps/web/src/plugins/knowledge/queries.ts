import { queryOptions, useQuery } from "@tanstack/react-query";
import { knowledgeApi } from "@/api";
import { KnowledgeService } from "@/api/generated/services/KnowledgeService";

export interface KnowledgeListFilters {
  tag?: string | null;
  status?: string | null;
}

export const knowledgeKeys = {
  all: ["knowledge"] as const,
  lists: () => [...knowledgeKeys.all, "list"] as const,
  list: ({ tag = null, status = null }: KnowledgeListFilters = {}) =>
    [...knowledgeKeys.lists(), { tag, status }] as const,
  notes: () => [...knowledgeKeys.all, "note"] as const,
  note: (path: string) => [...knowledgeKeys.notes(), path] as const,
  backlinks: (path: string) => [...knowledgeKeys.all, "backlinks", path] as const,
  /** Documents citing a run or an experiment. */
  citations: (kind: "run" | "experiment", experimentId: string, runId: string | null) =>
    [...knowledgeKeys.all, "citations", kind, experimentId, runId] as const,
  /** Documents citing an asset (`molab:asset/<id>`). */
  assetCitations: (assetId: string) =>
    [...knowledgeKeys.all, "citations", "asset", assetId] as const,
};

/** Knowledge documents that cite a run (or an experiment). */
export const entityCitationsQueryOptions = (
  kind: "run" | "experiment",
  projectId: string,
  experimentId: string,
  runId: string | null,
) =>
  queryOptions({
    queryKey: knowledgeKeys.citations(kind, experimentId, runId),
    queryFn: async () =>
      (await KnowledgeService.entityBacklinks(kind, projectId, experimentId, runId)).backlinks,
    staleTime: 30_000,
  });

/** Knowledge documents whose links cite an asset (L08 Cited in). */
export const assetCitationsQueryOptions = (assetId: string) =>
  queryOptions({
    queryKey: knowledgeKeys.assetCitations(assetId),
    queryFn: async () =>
      (await KnowledgeService.entityBacklinks("asset", null, null, null, assetId)).backlinks,
    staleTime: 60_000,
  });

export const knowledgeListQueryOptions = (filters: KnowledgeListFilters = {}) =>
  queryOptions({
    queryKey: knowledgeKeys.list(filters),
    queryFn: () => knowledgeApi.listKnowledge(filters),
    staleTime: 30_000,
  });

export const knowledgeNoteQueryOptions = (path: string) =>
  queryOptions({
    queryKey: knowledgeKeys.note(path),
    queryFn: () => knowledgeApi.getNote(path),
    staleTime: 30_000,
  });

export const knowledgeBacklinksQueryOptions = (path: string) =>
  queryOptions({
    queryKey: knowledgeKeys.backlinks(path),
    queryFn: () => knowledgeApi.getBacklinks(path),
    staleTime: 30_000,
  });

export const useKnowledgeListQuery = (filters: KnowledgeListFilters = {}, enabled = true) =>
  useQuery({ ...knowledgeListQueryOptions(filters), enabled });

export const useKnowledgeNoteQuery = (path: string, enabled = true) =>
  useQuery({ ...knowledgeNoteQueryOptions(path), enabled: enabled && path.length > 0 });

export const useKnowledgeBacklinksQuery = (path: string, enabled = true) =>
  useQuery({ ...knowledgeBacklinksQueryOptions(path), enabled: enabled && path.length > 0 });
