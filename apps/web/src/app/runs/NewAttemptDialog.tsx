/**
 * New attempt (Figma L04-9, L13 dialog): the mode as a segmented choice with
 * one sentence of what it will do, the attempt it is based on, the target, and
 * whether to recompute everything. Resume is preselected after a failure. The
 * run's parameters and inputs are immutable; this creates one new attempt.
 */

import {
  Checkbox,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@molcrafts/ui";
import { useQuery } from "@tanstack/react-query";
import { type JSX, useMemo, useState } from "react";
import { runsApi } from "@/api";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { attemptTarget, clockOf } from "@/app/renderers/run/runStory";
import {
  bypassCacheFor,
  canCancel,
  type ExecutionModeValue,
  executionModeOptions,
  isTerminalStatus,
} from "@/app/runs/runLifecycle";
import { executionJournalQueryOptions } from "@/app/state/entityQueries";
import { normalizeStatus, statusWord } from "@/app/status/vocabulary";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import { AppDialog } from "@/components/dialog/AppDialog";
import { cn } from "@/lib/utils";
import { normalizeTaskGraph } from "@/plugins/workflow/flowgram-document";

/** What the dialog opens with: a mode, and for "from scratch" the cache bypassed. */
export interface NewAttemptRequest {
  mode: ExecutionModeValue;
  bypassCache?: boolean;
}

export const targetsQueryOptions = () => ({
  queryKey: ["targets", "list"] as const,
  queryFn: async () => (await TargetsService.listTargetsEndpoint()).targets,
  staleTime: 60_000,
});

const MODE_LABEL: Record<ExecutionModeValue, string> = {
  initial: "Start",
  resume: "Resume",
  rerun: "Rerun",
  reproduce: "Reproduce",
};

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? "" : "s"}`;

/** One sentence of what the chosen mode will do, read off the base attempt's journal. */
const modeSentence = (
  mode: ExecutionModeValue,
  base: ExecutionRecordSummary | null,
  tasks: readonly { label?: string; id: string; status?: string }[],
  bypass: boolean,
): string => {
  const id = base?.executionId ?? "the latest attempt";
  if (mode === "initial") return "Run every task for the first time.";
  if (mode === "reproduce")
    return `Recompute every task to check ${id} reproduces; the cache is bypassed.`;
  if (mode === "rerun") {
    return bypass
      ? "Run every task again from scratch."
      : "Run the same definition again; unchanged tasks may come from the cache.";
  }
  const done = tasks.filter((task) => normalizeStatus(task.status ?? "") === "succeeded");
  const rest = tasks.length - done.length;
  if (tasks.length === 0) return `Continue from ${id}: finished tasks are reused.`;
  const reused =
    done.length === 0
      ? "nothing is reused"
      : done.length === 1
        ? `${done[0]?.label || done[0]?.id} is reused`
        : `${plural(done.length, "task")} are reused`;
  return `Continue from ${id}: ${reused}, ${plural(rest, "task")} run again.`;
};

export interface NewAttemptDialogProps {
  run: RunSummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The mode it opens on; the best enabled one when absent. */
  request: NewAttemptRequest | null;
  /** The attempt the page shows: the default base when it is finished. */
  pageExecutionId: string | null;
  onCreated: (execution: { id: string; target: string }) => void;
}

export function NewAttemptDialog({
  run,
  open,
  onOpenChange,
  request,
  pageExecutionId,
  onCreated,
}: NewAttemptDialogProps): JSX.Element {
  const history = run.executionHistory;
  const finished = useMemo(
    () => [...history].reverse().filter((execution) => isTerminalStatus(execution.status)),
    [history],
  );
  const blocking = [...history].reverse().find((execution) => canCancel(execution.status)) ?? null;
  const defaultBase =
    finished.find((execution) => execution.executionId === pageExecutionId) ?? finished[0] ?? null;
  const [baseId, setBaseId] = useState<string | null>(null);
  const base = finished.find((execution) => execution.executionId === baseId) ?? defaultBase;
  const options = executionModeOptions({
    attempts: history.length,
    basedOnStatus: base?.status ?? null,
    blockingExecutionId: blocking?.executionId ?? null,
  });
  const preferred = (): ExecutionModeValue => {
    const enabled = (value: ExecutionModeValue) =>
      options.find((option) => option.value === value)?.enabled;
    if (request && enabled(request.mode)) return request.mode;
    if (enabled("initial")) return "initial";
    if (enabled("resume")) return "resume";
    if (enabled("rerun")) return "rerun";
    return options.find((option) => option.enabled)?.value ?? "rerun";
  };
  const [chosen, setChosen] = useState<ExecutionModeValue | null>(null);
  const mode = chosen ?? preferred();
  const [bypassChosen, setBypassChosen] = useState<boolean | null>(null);
  const bypass = bypassChosen ?? Boolean(request?.bypassCache);
  const [targetChosen, setTargetChosen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targets = useQuery({ ...targetsQueryOptions(), enabled: open });
  const targetNames = (targets.data ?? []).map((target) => target.name);
  const baseTarget = attemptTarget(base ?? undefined);
  const target =
    targetChosen ??
    (baseTarget && targetNames.includes(baseTarget)
      ? baseTarget
      : targetNames.includes("local")
        ? "local"
        : (targetNames[0] ?? "local"));

  const journal = useQuery({
    ...executionJournalQueryOptions(
      run.projectId,
      run.experimentId,
      run.id,
      base?.executionId ?? "",
    ),
    enabled: open && base !== null,
  });
  const tasks = journal.data ? normalizeTaskGraph(journal.data).task_configs : [];
  const selected = options.find((option) => option.value === mode);
  // Resume first: after a failure it is the usual next step (L04-9).
  const ORDER: ExecutionModeValue[] = ["initial", "resume", "rerun", "reproduce"];
  const choices = options
    .filter((option) => option.value !== "initial" || history.length === 0)
    .sort((left, right) => ORDER.indexOf(left.value) - ORDER.indexOf(right.value));

  const reset = (): void => {
    setBaseId(null);
    setChosen(null);
    setBypassChosen(null);
    setTargetChosen(null);
    setError(null);
  };

  const create = async (): Promise<void> => {
    if (!selected?.enabled) return;
    setBusy(true);
    setError(null);
    try {
      const execution = await runsApi.createExecution(run.projectId, run.experimentId, run.id, {
        mode: mode as ExecutionAttemptCreateRequest.mode,
        ...(base ? { basedOnExecutionId: base.executionId } : {}),
        bypassCache: bypassCacheFor(mode, bypass),
        target,
      });
      onOpenChange(false);
      reset();
      onCreated({ id: execution.id, target });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
      title="New attempt"
      size="form"
      primaryLabel={history.length === 0 ? "Start" : "Create attempt"}
      busyLabel="Creating…"
      busy={busy}
      primaryDisabled={!selected?.enabled}
      onPrimary={create}
      error={error}
    >
      <div className="grid gap-4">
        {choices.length > 1 ? (
          <div className="grid gap-2">
            <Label id="attempt-mode-label">Mode</Label>
            <fieldset
              aria-labelledby="attempt-mode-label"
              className="flex w-max items-center gap-hairline rounded-hairline bg-muted p-hairline"
            >
              {choices.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={option.value === mode}
                  disabled={!option.enabled}
                  title={option.reason ?? option.description}
                  onClick={() => setChosen(option.value)}
                  className={cn(
                    "h-6 rounded-hairline px-3 text-body text-muted-foreground",
                    "hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                    "disabled:opacity-50 disabled:hover:text-muted-foreground",
                    option.value === mode && "bg-background text-foreground",
                  )}
                >
                  {MODE_LABEL[option.value]}
                </button>
              ))}
            </fieldset>
            <p className="text-label text-muted-foreground">
              {selected?.enabled
                ? modeSentence(mode, base, tasks, bypass)
                : (selected?.reason ?? selected?.description)}
            </p>
          </div>
        ) : null}
        {finished.length > 0 ? (
          <div className="grid gap-2">
            <Label htmlFor="attempt-base">Based on</Label>
            <Select
              value={base?.executionId ?? ""}
              onValueChange={(value) => {
                if (!value) return;
                setBaseId(value);
                setChosen(null);
              }}
            >
              <SelectTrigger id="attempt-base" className="font-mono">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {finished.map((execution) => (
                  <SelectItem
                    key={execution.executionId}
                    value={execution.executionId}
                    className="font-mono"
                  >
                    {[
                      execution.executionId,
                      statusWord(execution.status).toLowerCase(),
                      clockOf(execution.startedAt ?? execution.createdAt),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
        {blocking ? (
          <p className="text-label text-foreground">
            <span className="font-mono">{blocking.executionId}</span> is still{" "}
            {statusWord(blocking.status).toLowerCase()}. Stop it before starting another attempt.
          </p>
        ) : null}
        <div className="grid gap-2">
          <Label htmlFor="attempt-target">Target</Label>
          <Select
            value={target}
            // Radix reports "" when the list it holds is replaced (targets arriving); not a choice.
            onValueChange={(value) => value && setTargetChosen(value)}
          >
            <SelectTrigger id="attempt-target">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {targetNames.length === 0 ? <SelectItem value="local">local</SelectItem> : null}
              {targetNames.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="attempt-bypass-cache"
            checked={mode === "reproduce" || bypass}
            disabled={mode === "reproduce"}
            onCheckedChange={(value) => setBypassChosen(value === true)}
          />
          <Label htmlFor="attempt-bypass-cache" className="font-normal">
            Recompute everything (bypass cache)
          </Label>
        </div>
      </div>
    </AppDialog>
  );
}
