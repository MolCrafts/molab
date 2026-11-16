/**
 * The snapshot editor tabs are described from, plus the knowledge documents'
 * names (L10: a document's tab is its name, not its file slug).
 */

import { useMemo } from "react";
import type { WorkspaceSnapshot } from "@/app/types";
import { useKnowledgeListQuery } from "@/plugins/knowledge/queries";

export const useTabSnapshot = <T extends WorkspaceSnapshot>(
  snapshot: T,
): T & { knowledge: ReadonlyArray<{ relPath: string; name: string }> } => {
  const list = useKnowledgeListQuery();
  const notes = list.data?.notes;
  return useMemo(() => ({ ...snapshot, knowledge: notes ?? [] }), [snapshot, notes]);
};
