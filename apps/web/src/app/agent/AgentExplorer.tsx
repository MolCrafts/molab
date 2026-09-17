import { Bot, Copy, ExternalLink, Plus, Settings, Sparkles, Trash2 } from "lucide-react";
import { usePermissions, withWriteGate } from "@/app/auth";
import { EMPTY_COPY, StatusBadge } from "@/app/components/entity";
import type { NavigationExplorerProps } from "@/app/navigation/sections";
import { type TreeNode, type TreeNodeAction, TreeView } from "@/app/panels/TreeView";
import { prefetchRenderer } from "@/app/renderers/lazyRenderers";
import { agentApi } from "@/app/state/api";
import type { AgentSessionSummary, Selection } from "@/app/types";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { LeftExplorer } from "@/components/layout/ExplorerShell";
import { Code as InlineCode } from "@/components/ui/code";
import { WorkbenchIconAction } from "@/components/workbench";
import { agentTaskDisplayTitle } from "@/lib/agent-task-title";

const copyText = async (text: string): Promise<void> => {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    console.warn("Failed to copy agent task ID:", error);
  }
};

const shortenTaskTitle = (session: AgentSessionSummary): string => {
  const clean = agentTaskDisplayTitle(session, 200);
  const sentenceEnd = clean.search(/[.!?。！？]/);
  const clipped = sentenceEnd > 0 ? clean.slice(0, sentenceEnd) : clean;
  return clipped.length > 32 ? `${clipped.slice(0, 30).trim()}…` : clipped;
};

export const buildAgentExplorerNodes = ({
  sessions,
  onSelect,
  onDelete,
  onPrefetchSession,
  writeDeniedReason,
}: {
  sessions: AgentSessionSummary[];
  onSelect: (selection: Selection) => void;
  onDelete: (session: AgentSessionSummary) => void;
  onPrefetchSession?: (session: AgentSessionSummary) => void;
  writeDeniedReason: string | null;
}): TreeNode[] =>
  sessions.map((session) => ({
    id: session.id,
    label: shortenTaskTitle(session),
    hoverTitle: session.goal,
    icon: Bot,
    iconClassName: "text-muted-foreground",
    right: <StatusBadge status={session.status} size="sm" dot showLabel={false} />,
    onPrefetch: () => onPrefetchSession?.(session),
    onSelect: () => onSelect({ objectType: "agent", objectId: session.id }),
    actions: [
      {
        id: "open",
        label: "Open task",
        icon: ExternalLink,
        onSelect: () => onSelect({ objectType: "agent", objectId: session.id }),
      },
      {
        id: "copy-id",
        label: "Copy task ID",
        icon: Copy,
        onSelect: () => void copyText(session.id),
      },
      withWriteGate<TreeNodeAction>(
        {
          id: "delete",
          label: "Delete task",
          icon: Trash2,
          destructive: true,
          separatorBefore: true,
          onSelect: () => onDelete(session),
        },
        writeDeniedReason,
      ),
    ],
  }));

/** Complete Agent task explorer, including task commands and confirmation state. */
export const AgentExplorer = ({
  snapshot,
  selection,
  onSelect,
  onRefresh,
}: Pick<
  NavigationExplorerProps,
  "snapshot" | "selection" | "onSelect" | "onRefresh"
>): JSX.Element => {
  const { writeDeniedReason } = usePermissions();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();

  const deleteTask = async (session: AgentSessionSummary): Promise<void> => {
    const confirmed = await confirm({
      title: "Delete agent task?",
      description: (
        <>
          Agent task{" "}
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">
            {session.id}
          </InlineCode>{" "}
          will be removed from the task list. If it is running, its current turn will be cancelled.
        </>
      ),
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;

    try {
      await agentApi.deleteSession(session.id);
      if (selection?.objectType === "agent" && selection.objectId === session.id) {
        onSelect({ objectType: "agent", objectId: "new" });
      }
      onRefresh();
    } catch (error) {
      console.error("Failed to delete agent task:", error);
      void alert({
        title: "Failed to delete agent task",
        description: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const nodes = buildAgentExplorerNodes({
    sessions: snapshot.agentSessions,
    onSelect,
    onDelete: (session) => void deleteTask(session),
    onPrefetchSession: () => prefetchRenderer("agent"),
    writeDeniedReason,
  });
  const actions = (
    <>
      <WorkbenchIconAction
        label="Agent settings"
        kind="ghost"
        onClick={() => onSelect({ objectType: "agent", objectId: "settings" })}
        title="Agents, model, skills, tools, and MCP"
      >
        <Settings className="size-icon" />
      </WorkbenchIconAction>
      <WorkbenchIconAction
        label="New agent task"
        kind="ghost"
        deniedReason={writeDeniedReason}
        onClick={() => onSelect({ objectType: "agent", objectId: "new" })}
      >
        <Plus className="size-icon" />
      </WorkbenchIconAction>
    </>
  );

  return (
    <>
      <LeftExplorer title="Agent tasks" actions={actions}>
        <TreeView
          nodes={nodes}
          activeId={selection?.objectId}
          emptyIcon={<Sparkles className="h-control w-control" />}
          emptyTitle={EMPTY_COPY.agentSessions.title}
          emptyDescription={EMPTY_COPY.agentSessions.description}
        />
      </LeftExplorer>
      {confirmDialog}
      {alertDialog}
    </>
  );
};
