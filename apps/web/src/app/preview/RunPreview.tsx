/**
 * Run and attempt Previews (Figma L12-1, L12-9): verdict · evidence · the
 * attempt's tasks on a clock · the state's primary action + Logs. The run comes
 * from the entity catalog, or from the workspace runs table when a chart or a
 * table names a run whose experiment is not loaded.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { activeWorkspace, itemFromRunSummary } from "@/app/compare/entries";
import { itemKey } from "@/app/compare/types";
import { useCompareSet } from "@/app/compare/useCompareSet";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { runPath } from "@/app/entities/paths";
import { runVerdict, taskClock } from "@/app/renderers/run/runStory";
import { TaskClock } from "@/app/renderers/run/TaskClock";
import { runSummaryFromRow } from "@/app/runs/projections";
import { canCancel, canResume, isTerminalStatus } from "@/app/runs/runLifecycle";
import { runLabel } from "@/app/runs/runTitle";
import { confirmAndStopExecution } from "@/app/runs/stopExecution";
import { workspaceRunsQueryOptions } from "@/app/runs/useWorkspaceRuns";
import { executionJournalQueryOptions, journalRefetchInterval } from "@/app/state/entityQueries";
import type { ExecutionRecordSummary, RunSummary, WorkspaceSnapshot } from "@/app/types";
import { useAlert, useConfirm } from "@/components/ConfirmDialog";
import { WorkbenchAction } from "@/components/workbench";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";
import { type PreviewCopy, PreviewFrame, PreviewKV } from "./PreviewFrame";
import { PreviewGone, PreviewLoading } from "./PreviewStates";
import { PreviewEvidence, PreviewVerdict } from "./previewParts";
import type { PreviewTarget } from "./target";

type RunTarget = Extract<PreviewTarget, { kind: "run" | "attempt" }>;

/**
 * Run ids repeat across served workspaces. A target from another workspace is
 * read from the runs table only, and it is read-only here: its journal and its
 * Stop / Resume live behind that workspace, which ↗ activates first.
 */
const isForeign = (target: RunTarget, snapshot: WorkspaceSnapshot): boolean => {
  const active = activeWorkspace(snapshot.workspaces);
  return Boolean(target.workspaceKey && active && target.workspaceKey !== active.key);
};

const useRun = (
  target: RunTarget,
  snapshot: WorkspaceSnapshot,
): { run: RunSummary | null; loading: boolean } => {
  const fromCatalog = isForeign(target, snapshot)
    ? null
    : (snapshot.runs.find((run) => run.id === target.runId) ?? null);
  const table = useQuery({ ...workspaceRunsQueryOptions(), enabled: fromCatalog === null });
  const row = table.data?.runs.find(
    (candidate) =>
      candidate.id === target.runId &&
      (!target.workspaceKey || candidate.workspaceKey === target.workspaceKey),
  );
  return {
    run: fromCatalog ?? (row ? runSummaryFromRow(row) : null),
    loading: fromCatalog === null && table.isPending,
  };
};

const executorText = (execution: ExecutionRecordSummary | undefined): string | null => {
  const target = execution?.executor?.target ?? execution?.executor?.backend;
  return typeof target === "string" && target ? target : null;
};

const clock = (iso: string | null | undefined): string | null =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;

interface RunPreviewProps {
  target: RunTarget;
  snapshot: WorkspaceSnapshot;
  /** Re-read the workspace after an action (Stop). */
  onRefresh: () => void;
  onOpen: (target: PreviewTarget, path?: string) => void;
  onOpenInBackground: () => void;
  onClose: () => void;
}

export const RunPreview = ({
  target,
  snapshot,
  onRefresh,
  onOpen,
  onOpenInBackground,
  onClose,
}: RunPreviewProps): JSX.Element => {
  const { run, loading } = useRun(target, snapshot);
  const foreign = isForeign(target, snapshot);
  const queryClient = useQueryClient();
  const history = run?.executionHistory ?? [];
  const attempt =
    target.kind === "attempt"
      ? history.find((item) => item.executionId === target.executionId)
      : history.at(-1);
  const journal = useQuery({
    ...executionJournalQueryOptions(
      target.projectId,
      target.experimentId,
      target.runId,
      attempt?.executionId ?? "",
    ),
    enabled: Boolean(attempt) && !foreign,
    refetchInterval: journalRefetchInterval(attempt?.status),
  });
  const journalKey = executionJournalQueryOptions(
    target.projectId,
    target.experimentId,
    target.runId,
    attempt?.executionId ?? "",
  ).queryKey;
  const graph = useMemo(
    () => (journal.data ? normalizeTaskGraph(journal.data) : null),
    [journal.data],
  );
  const now = useMemo(() => Date.now(), []);
  const tasks = useMemo(() => taskClock(graph, attempt ?? null, now), [graph, attempt, now]);
  const compare = useCompareSet();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const { alert, dialog: alertDialog } = useAlert();

  const label = run ? runLabel(run) : ("label" in target && target.label) || target.runId;
  const frame = {
    title: target.kind === "attempt" ? target.executionId : label,
    mono: true,
    onOpen: () => onOpen(target),
    onOpenInBackground,
    onClose,
  };
  if (loading) return <PreviewLoading {...frame} kindLabel="run" />;
  if (!run || !attempt) {
    return run && !attempt && target.kind === "run" ? (
      <PreviewFrame
        {...frame}
        lead={<StatusIcon status="pending" className="size-icon" />}
        context={`run · ${run.id}`}
      >
        <PreviewVerdict status="none" subject="Not run yet" />
      </PreviewFrame>
    ) : (
      <PreviewGone {...frame} kindLabel={target.kind === "attempt" ? "attempt" : "run"} />
    );
  }

  // The verdict reads the attempt this Preview is about, not always the latest.
  const scoped: RunSummary = {
    ...run,
    executionHistory: history.slice(0, history.indexOf(attempt) + 1),
  };
  const verdict = runVerdict(scoped, graph, now);
  const status = attempt.status;
  const where = executorText(attempt);
  const started = clock(attempt.startedAt ?? attempt.createdAt);
  const context = [
    target.kind === "attempt" ? `attempt · ${label}` : `run · ${run.id}`,
    target.kind === "run" ? attempt.executionId : null,
    where,
    started ? `started ${started}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const workspace = activeWorkspace(snapshot.workspaces);
  const project = snapshot.projects.find((item) => item.id === run.projectId);
  const experiment = snapshot.experiments.find((item) => item.id === run.experimentId);
  const compareItem = itemFromRunSummary(run, {
    workspaceKey: target.workspaceKey ?? workspace?.key ?? "",
    workspaceLabel: workspace?.label ?? "",
    projectName: project?.name ?? run.projectId,
    experimentName: experiment?.name ?? run.experimentId,
  });
  const pinned = compare.has(itemKey(compareItem.ref));
  const logsTarget = runPath(run.projectId, run.experimentId, run.id, "logs");

  const latest = attempt === history.at(-1);
  // The create-attempt dialog continues from the latest attempt; an older one
  // has nothing to resume from here. A foreign run is read-only (↗ first).
  const primary = foreign ? null : latest && canResume(attempt.status) ? (
    <WorkbenchAction
      kind="primary"
      size="content"
      className="h-shell-button rounded-hairline bg-accent px-3 font-normal text-accent-foreground hover:bg-accent-hover"
      // The run page owns the create-attempt dialog (mode, target, cache);
      // `new=resume` opens it with Resume preselected.
      onClick={() =>
        onOpen(
          target,
          runPath(run.projectId, run.experimentId, run.id, undefined, { create: "resume" }),
        )
      }
    >
      Resume
    </WorkbenchAction>
  ) : canCancel(attempt.status) ? (
    <WorkbenchAction
      kind="secondary"
      size="content"
      className="h-shell-button rounded-hairline px-3 font-normal"
      onClick={() =>
        void confirmAndStopExecution({
          run,
          execution: attempt,
          confirm,
          alert,
          onStopped: () => {
            void queryClient.invalidateQueries({ queryKey: ["workspace-runs"] });
            void queryClient.invalidateQueries({ queryKey: journalKey });
            onRefresh();
          },
        })
      }
    >
      Stop {attempt.executionId}
    </WorkbenchAction>
  ) : isTerminalStatus(attempt.status) ? (
    <WorkbenchAction
      kind="secondary"
      size="content"
      className="h-shell-button rounded-hairline px-3 font-normal"
      aria-pressed={pinned}
      onClick={() => (pinned ? compare.remove(itemKey(compareItem.ref)) : compare.add(compareItem))}
    >
      {pinned ? "Unpin" : "Compare"}
    </WorkbenchAction>
  ) : null;

  const copies: PreviewCopy[] = [
    { label: "Run id", value: run.id },
    { label: "Path", value: run.path },
    ...(run.definitionHash ? [{ label: "Definition hash", value: run.definitionHash }] : []),
  ];

  return (
    <PreviewFrame
      {...frame}
      lead={<StatusIcon status={status} className="size-icon" />}
      context={context}
      announcement={`${frame.title}. ${verdict.headline}`}
      copies={copies}
      actions={
        <>
          {primary}
          <WorkbenchAction
            kind="secondary"
            size="content"
            className="h-shell-button rounded-hairline bg-interactive px-3 font-normal"
            onClick={() => onOpen(target, logsTarget)}
          >
            Logs
          </WorkbenchAction>
          {confirmDialog}
          {alertDialog}
        </>
      }
    >
      <PreviewVerdict
        status={status}
        subject={verdict.label ?? undefined}
        right={verdict.elapsed}
      />
      {verdict.evidence ? <PreviewEvidence>{verdict.evidence}</PreviewEvidence> : null}
      {target.kind === "attempt" ? (
        <div className="pl-6">
          <PreviewKV label="mode" mono={false}>
            {attempt.mode}
          </PreviewKV>
          {where ? (
            <PreviewKV label="target" mono={false}>
              {where}
            </PreviewKV>
          ) : null}
          {started ? (
            <PreviewKV label="started" mono={false}>
              {[started, clock(attempt.finishedAt)].filter(Boolean).join(" → ")}
            </PreviewKV>
          ) : null}
        </div>
      ) : null}
      {tasks.length > 0 ? <TaskClock rows={tasks} labelWidth="w-32" /> : null}
    </PreviewFrame>
  );
};
