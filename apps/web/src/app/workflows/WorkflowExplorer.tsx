import { Copy, ExternalLink, FlaskConical, RefreshCw, Workflow } from "lucide-react";
import { EMPTY_COPY, StatusBadge } from "@/app/components/entity";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { type TreeNode, TreeView } from "@/app/panels/TreeView";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { WorkbenchIconAction } from "@/components/workbench";

const copyText = async (text: string): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    console.warn("Failed to copy workflow ID:", error);
  }
};

export const buildWorkflowExplorerNodes = ({
  snapshot,
  searchQuery,
  onSelect,
}: Pick<NavigationExplorerProps, "snapshot" | "searchQuery" | "onSelect">): TreeNode[] => {
  const lower = searchQuery.toLowerCase();
  return snapshot.workflows
    .filter(
      (workflow) =>
        !lower ||
        workflow.name.toLowerCase().includes(lower) ||
        workflow.summary.toLowerCase().includes(lower),
    )
    .map((workflow) => ({
      id: workflow.id,
      label: workflow.name,
      icon: Workflow,
      iconClassName: "text-muted-foreground",
      right: <StatusBadge status={workflow.status} size="sm" />,
      onSelect: () =>
        onSelect({ objectType: "workflow", objectId: workflow.id, workflowId: workflow.id }),
      actions: [
        {
          id: "open",
          label: "Open workflow",
          icon: ExternalLink,
          onSelect: () =>
            onSelect({ objectType: "workflow", objectId: workflow.id, workflowId: workflow.id }),
        },
        {
          id: "open-experiment",
          label: "Open experiment",
          icon: FlaskConical,
          onSelect: () => onSelect({ objectType: "experiment", objectId: workflow.experimentId }),
        },
        {
          id: "copy-id",
          label: "Copy workflow ID",
          icon: Copy,
          onSelect: () => void copyText(workflow.id),
        },
      ],
    }));
};

/** Compatibility explorer for legacy /workflows routes; intentionally absent from the rail. */
export const WorkflowExplorer = (
  props: Pick<
    NavigationExplorerProps,
    "snapshot" | "selection" | "searchQuery" | "onSelect" | "onRefresh"
  >,
): JSX.Element => (
  <LeftExplorer
    title="Workflows"
    actions={
      <WorkbenchIconAction label="Refresh workflows" kind="ghost" onClick={props.onRefresh}>
        <RefreshCw className="size-4" />
      </WorkbenchIconAction>
    }
  >
    <TreeView
      nodes={buildWorkflowExplorerNodes(props)}
      activeId={props.selection?.objectId}
      emptyTitle={EMPTY_COPY.entries.title}
    />
  </LeftExplorer>
);
