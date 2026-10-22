import { queryOptions, useQuery } from "@tanstack/react-query";
import { knowledgeApi } from "@/api";

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
};

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
