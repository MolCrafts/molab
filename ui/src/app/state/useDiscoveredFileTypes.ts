import { useCallback } from "react";
import type { RunFilesResponse } from "@/app/state/api";
import { useRunFilesQuery } from "@/app/state/queries/runs";
import type { SemanticObjectType } from "@/app/types";
import type { DiscoveredPlugin } from "@/lib/file-type-discovery";
import { discoverPluginsForObject, flattenFileNodes } from "@/lib/file-type-discovery";

interface RunCoords {
  projectId: string;
  experimentId: string;
  runId: string;
}

const EMPTY_DISCOVERED: DiscoveredPlugin[] = [];

interface UseDiscoveredFileTypesResult {
  discovered: DiscoveredPlugin[];
  loading: boolean;
  error: string | null;
}

export const useDiscoveredFileTypesForRun = (
  coords: RunCoords | null,
  objectType: SemanticObjectType = "run",
): UseDiscoveredFileTypesResult => {
  // Discovery is a pure projection of the file tree, so it rides on the shared
  // `runFiles` cache entry via `select` — opening a run twice discovers once.
  const select = useCallback(
    (response: RunFilesResponse): DiscoveredPlugin[] =>
      discoverPluginsForObject(objectType, flattenFileNodes(response.nodes)),
    [objectType],
  );
  const query = useRunFilesQuery<DiscoveredPlugin[]>(coords, { select });

  return {
    discovered: query.data ?? EMPTY_DISCOVERED,
    loading: query.isPending && coords !== null,
    error: query.error instanceof Error ? query.error.message : null,
  };
};
