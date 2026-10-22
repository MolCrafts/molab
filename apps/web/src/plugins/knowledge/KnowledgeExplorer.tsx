import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { DocTree } from "./DocTree";

/** Feature-owned navigation contribution for Knowledge documents. */
export const KnowledgeExplorer = ({
  snapshot,
  selection,
  onSelect,
}: Pick<NavigationExplorerProps, "snapshot" | "selection" | "onSelect">): JSX.Element => (
  <LeftExplorer title="Knowledge">
    <DocTree snapshot={snapshot} activeId={selection?.objectId} onSelect={onSelect} />
  </LeftExplorer>
);
