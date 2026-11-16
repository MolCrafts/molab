import { queryOptions, useQuery } from "@tanstack/react-query";
import { historyApi, knowledgeApi } from "@/api";
import { KnowledgeService } from "@/api/generated/services/KnowledgeService";

export interface KnowledgeListFilters {
  tag?: string | null;
  status?: string | null;
}

export const knowledgeKeys = {
  all: ["knowledge"] as const,
  graph: () => [...knowledgeKeys.all, "graph"] as const,
  lists: () => [...knowledgeKeys.all, "list"] as const,
  list: ({ tag = null, status = null }: KnowledgeListFilters = {}) =>
    [...knowledgeKeys.lists(), { tag, status }] as const,
  notes: () => [...knowledgeKeys.all, "note"] as const,
  note: (path: string) => [...knowledgeKeys.notes(), path] as const,
  /** One git version of a document: immutable once committed. */
  noteVersion: (path: string, version: number) =>
    [...knowledgeKeys.note(path), "version", version] as const,
  /** A document's git versions and whether its working copy is uncommitted. */
  versions: (path: string) => [...knowledgeKeys.all, "versions", path] as const,
  /** One version's diff against the working copy. */
  versionDiff: (path: string, version: number) =>
    [...knowledgeKeys.versions(path), version] as const,
  backlinks: (path: string) => [...knowledgeKeys.all, "backlinks", path] as const,
  /** A Manuscript's bibliography: it changes with the Manuscript and with the Literature it cites. */
  bibliography: (path: string) => [...knowledgeKeys.all, "bibliography", path] as const,
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

export const knowledgeNoteQueryOptions = (path: string, version: number | null = null) =>
  queryOptions({
    queryKey:
      version === null ? knowledgeKeys.note(path) : knowledgeKeys.noteVersion(path, version),
    queryFn: () => knowledgeApi.getNote(path, version),
    // A committed version never changes; the live file does.
    staleTime: version === null ? 30_000 : Number.POSITIVE_INFINITY,
  });

export const knowledgeBacklinksQueryOptions = (path: string) =>
  queryOptions({
    queryKey: knowledgeKeys.backlinks(path),
    queryFn: () => knowledgeApi.getBacklinks(path),
    staleTime: 30_000,
  });

export const knowledgeBibliographyQueryOptions = (path: string) =>
  queryOptions({
    queryKey: knowledgeKeys.bibliography(path),
    queryFn: () => knowledgeApi.docBibliography(path),
    staleTime: 30_000,
    // 422 names the \cite key no Literature answers; retrying does not change that.
    retry: false,
  });

export const useKnowledgeBibliographyQuery = (path: string, enabled = true) =>
  useQuery({ ...knowledgeBibliographyQueryOptions(path), enabled: enabled && path.length > 0 });

export const useKnowledgeListQuery = (filters: KnowledgeListFilters = {}, enabled = true) =>
  useQuery({ ...knowledgeListQueryOptions(filters), enabled });

export const useKnowledgeNoteQuery = (
  path: string,
  enabled = true,
  version: number | null = null,
) => useQuery({ ...knowledgeNoteQueryOptions(path, version), enabled: enabled && path.length > 0 });

/** A document's git versions. History is optional: a refusal (422 above the served node) or an absent git hides the switcher. */
export const useKnowledgeVersionsQuery = (path: string, enabled = true) =>
  useQuery({
    queryKey: knowledgeKeys.versions(path),
    queryFn: () => historyApi.document(path),
    staleTime: 30_000,
    retry: false,
    enabled: enabled && path.length > 0,
  });

export const useKnowledgeVersionDiffQuery = (path: string, version: number, enabled = true) =>
  useQuery({
    queryKey: knowledgeKeys.versionDiff(path, version),
    queryFn: () => historyApi.document(path, version),
    staleTime: 30_000,
    retry: false,
    enabled,
  });

export const useKnowledgeBacklinksQuery = (path: string, enabled = true) =>
  useQuery({ ...knowledgeBacklinksQueryOptions(path), enabled: enabled && path.length > 0 });

/** The server owns document identity and typed link resolution. */
export const knowledgeGraphQueryOptions = () =>
  queryOptions({
    queryKey: knowledgeKeys.graph(),
    queryFn: () => KnowledgeService.getKnowledgeGraph(),
    staleTime: 30_000,
  });
