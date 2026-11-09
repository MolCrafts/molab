/**
 * Task and workflow-node Previews (Figma L12-2, L12-8). A task is a node of one
 * attempt (status, time, error); a node is a definition (type, inputs, edges)
 * and has no status. Upstream / downstream re-target the Preview.
 */

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { formatSpan } from "@/app/components/entity/gauges/scale";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { entityMeta } from "@/app/entities/kinds";
import { experimentPath } from "@/app/entities/paths";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import { statusWord } from "@/app/status/vocabulary";
import type { WorkspaceSnapshot } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";
import type { TaskGraphJson } from "@/plugins/workflow/task-graph-ir";
import { KindIcon, PreviewFrame, PreviewKV, PreviewLink, PreviewSubhead } from "./PreviewFrame";
import { PreviewGone, PreviewLoading } from "./PreviewStates";
import { PreviewEvidence, PreviewVerdict } from "./previewParts";
import type { PreviewTarget } from "./target";

type TaskTarget = Extract<PreviewTarget, { kind: "task" | "node" }>;

interface TaskPreviewProps {
  target: TaskTarget;
  snapshot: WorkspaceSnapshot;
  onPreview: (target: PreviewTarget) => void;
  onOpen: (target: PreviewTarget, path?: string) => void;
  onOpenInBackground: () => void;
  onClose: () => void;
}

const edges = (graph: TaskGraphJson | null | undefined, id: string) => ({
  upstream: (graph?.links ?? []).filter((edge) => edge.to === id).map((edge) => edge.from),
  downstream: (graph?.links ?? []).filter((edge) => edge.from === id).map((edge) => edge.to),
});

const showValue = (value: unknown): string =>
  typeof value === "string" ? value : JSON.stringify(value);

export const TaskPreview = ({
  target,
  snapshot,
  onPreview,
  onOpen,
  onOpenInBackground,
  onClose,
}: TaskPreviewProps): JSX.Element => {
  const run =
    target.kind === "task" ? snapshot.runs.find((item) => item.id === target.runId) : null;
  // The attempt the page had selected, else the latest one.
  const latest =
    (target.kind === "task" && target.executionId
      ? run?.executionHistory.find((item) => item.executionId === target.executionId)
      : undefined) ?? run?.executionHistory.at(-1);
  const journal = useQuery({
    ...executionJournalQueryOptions(
      target.projectId,
      target.experimentId,
      target.kind === "task" ? target.runId : "",
      latest?.executionId ?? "",
    ),
    enabled: target.kind === "task" && Boolean(latest),
    refetchInterval: journalRefetchInterval(latest?.status),
  });
  const attemptGraph = useMemo(
    () => (journal.data ? normalizeTaskGraph(journal.data) : null),
    [journal.data],
  );
  const definition =
    snapshot.workflows.find((workflow) => workflow.experimentId === target.experimentId)?.graph ??
    null;
  const graph = target.kind === "task" ? (attemptGraph ?? definition) : definition;
  const node = graph?.task_configs.find((item) => item.id === target.taskId) ?? null;
  const title = node?.label || target.taskId;
  const frame = { title, onOpen: () => onOpen(target), onOpenInBackground, onClose };

  if (target.kind === "task" && journal.isPending && latest) {
    return <PreviewLoading {...frame} kindLabel="task" />;
  }
  if (!node) return <PreviewGone {...frame} kindLabel="task" />;

  const { upstream, downstream } = edges(graph, node.id);
  const retarget = (taskId: string) =>
    onPreview(
      target.kind === "task"
        ? { ...target, taskId }
        : { kind: "node", projectId: target.projectId, experimentId: target.experimentId, taskId },
    );
  const nameOf = (id: string) => graph?.task_configs.find((item) => item.id === id)?.label || id;
  const edgeLinks = (ids: string[]) =>
    ids.length === 0 ? (
      <span className="text-muted-foreground">none</span>
    ) : (
      <span className="flex min-w-0 gap-2">
        {ids.map((id) => (
          <PreviewLink key={id} mono={false} onClick={() => retarget(id)}>
            {nameOf(id)}
          </PreviewLink>
        ))}
      </span>
    );

  const status = target.kind === "task" ? (node.status ?? "pending") : null;
  const start = node.startedAt ? Date.parse(node.startedAt) : null;
  const end = node.finishedAt ? Date.parse(node.finishedAt) : null;
  const took = start !== null && end !== null ? formatSpan(Math.max(0, end - start) / 1000) : null;
  const inputs = Object.entries(node.params ?? node.config ?? {}).slice(0, 6);

  return (
    <PreviewFrame
      {...frame}
      lead={
        status ? (
          <StatusIcon status={status} className="size-icon" />
        ) : (
          <KindIcon icon={entityMeta("task").icon} />
        )
      }
      context={target.kind === "task" ? `task · ${node.id}` : `task definition · ${node.type}`}
      announcement={status ? `${title}. ${statusWord(status)}` : title}
      copies={[{ label: "Task id", value: node.id }]}
      actions={
        target.kind === "node" ? (
          // The definition's outcome lives on the experiment's Overview, by task (L06).
          <DialogButton
            kind="secondary"
            onClick={() =>
              onOpen(
                {
                  kind: "experiment",
                  projectId: target.projectId,
                  experimentId: target.experimentId,
                },
                `${experimentPath(target.projectId, target.experimentId)}?by=task`,
              )
            }
          >
            Outcome in runs
          </DialogButton>
        ) : undefined
      }
    >
      {status ? (
        <>
          <PreviewVerdict status={status} subject={took ?? undefined} />
          {node.error ? <PreviewEvidence>{node.error}</PreviewEvidence> : null}
        </>
      ) : null}
      <div className="pl-6">
        <PreviewKV label="id">{node.id}</PreviewKV>
        <PreviewKV label="type">{node.type}</PreviewKV>
      </div>
      {target.kind === "node" && inputs.length > 0 ? (
        <>
          <PreviewSubhead>Inputs</PreviewSubhead>
          <div className="pl-6">
            {inputs.map(([key, value]) => (
              <PreviewKV key={key} label={key}>
                {showValue(value)}
              </PreviewKV>
            ))}
          </div>
        </>
      ) : null}
      <div className="pl-6">
        <PreviewKV label="upstream" mono={false}>
          {edgeLinks(upstream)}
        </PreviewKV>
        <PreviewKV label="downstream" mono={false}>
          {edgeLinks(downstream)}
        </PreviewKV>
      </div>
    </PreviewFrame>
  );
};
