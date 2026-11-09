import {
  Checkbox,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@molcrafts/ui";
import { Ban, Copy, Download, MoreHorizontal, Play, Plus } from "lucide-react";
import { type JSX, useEffect, useMemo, useRef, useState } from "react";
import { runsApi } from "@/api";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { usePermissions } from "@/app/auth";
import { HarvestDialog } from "@/app/components/HarvestDialog";
import {
  bypassCacheFor,
  canCancel,
  canHarvest,
  defaultExecutionMode,
  type ExecutionModeValue,
  executionModeOptions,
} from "@/app/runs/runLifecycle";
import type { RunSummary } from "@/app/types";
import { AppDialog } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";

export interface RunToolbarProps {
  run: RunSummary;
  selectedExecutionId: string | null;
  onRefresh: () => void;
  onCancel: () => Promise<void>;
  onDispatched?: (executionId: string) => void;
  onHarvested?: (path: string) => void;
  /** A Preview's Resume (`?attempt=new`): open the dialog with Resume chosen. */
  resumeRequested?: boolean;
  onResumeRequestHandled?: () => void;
}

export function RunToolbar({
  run,
  selectedExecutionId,
  onRefresh,
  onCancel,
  onDispatched,
  onHarvested,
  resumeRequested = false,
  onResumeRequestHandled,
}: RunToolbarProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const selectedExecution = run.executionHistory.find(
    (execution) => execution.executionId === selectedExecutionId,
  );
  const latestExecution = run.executionHistory[run.executionHistory.length - 1];
  const attempts = run.executionHistory.length;
  const predecessor = selectedExecution ?? latestExecution ?? null;
  const basedOnStatus = predecessor?.status ?? null;
  const blockingExecution =
    [...run.executionHistory].reverse().find((execution) => canCancel(execution.status)) ?? null;
  const blockingExecutionId =
    blockingExecution && blockingExecution.executionId !== predecessor?.executionId
      ? blockingExecution.executionId
      : null;
  const modeOptions = useMemo(
    () => executionModeOptions({ attempts, basedOnStatus, blockingExecutionId }),
    [attempts, basedOnStatus, blockingExecutionId],
  );
  const canCancelSelected = selectedExecution ? canCancel(selectedExecution.status) : false;
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ExecutionModeValue>(defaultExecutionMode(modeOptions));
  const [bypassCache, setBypassCache] = useState(false);
  const [target, setTarget] = useState("local");
  const [targets, setTargets] = useState<TargetResponse[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    TargetsService.listTargetsEndpoint()
      .then((response) => {
        if (cancelled) return;
        setTargets(response.targets);
        const names = response.targets.map((item) => item.name);
        setTarget(names.includes("local") ? "local" : (names[0] ?? "local"));
      })
      .catch(() => {
        if (!cancelled) setTargets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // A Resume request must open on Resume, not on whatever the default would
  // be — chosen once per opening, so a refresh while open keeps the choice.
  const resumeOnOpen = useRef(false);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the mode is chosen when the dialog opens, not on every refresh
  useEffect(() => {
    if (!open) return;
    const options = executionModeOptions({ attempts, basedOnStatus, blockingExecutionId });
    const resume = options.find((option) => option.value === "resume" && option.enabled);
    setMode(resumeOnOpen.current && resume ? "resume" : defaultExecutionMode(options));
    resumeOnOpen.current = false;
  }, [open]);

  useEffect(() => {
    if (!resumeRequested) return;
    onResumeRequestHandled?.();
    // A viewer without write access gets no form that can only fail; an
    // already-open dialog keeps the mode its user chose.
    if (writeDeniedReason || open) return;
    resumeOnOpen.current = true;
    setOpen(true);
  }, [resumeRequested, onResumeRequestHandled, writeDeniedReason, open]);

  const selectedMode = useMemo(
    () => modeOptions.find((item) => item.value === mode),
    [mode, modeOptions],
  );

  const createExecution = async (): Promise<void> => {
    if (!selectedMode?.enabled) return;
    setBusy(true);
    setError(null);
    try {
      const execution = await runsApi.createExecution(run.projectId, run.experimentId, run.id, {
        mode: mode as ExecutionAttemptCreateRequest.mode,
        ...(selectedExecutionId ? { basedOnExecutionId: selectedExecutionId } : {}),
        bypassCache: bypassCacheFor(mode, bypassCache),
        target,
      });
      setOpen(false);
      toast.success("Execution created");
      onRefresh();
      onDispatched?.(execution.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-1">
      <AppDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setError(null);
        }}
        title="New attempt"
        message="Run parameters and scientific inputs are immutable. This creates one new physical attempt."
        size="form"
        primaryLabel="Create attempt"
        busyLabel="Creating…"
        busy={busy}
        primaryDisabled={!selectedMode?.enabled}
        onPrimary={createExecution}
        error={error}
        trigger={
          <WorkbenchIconAction label="Create execution" deniedReason={writeDeniedReason}>
            {run.executionHistory.length === 0 ? (
              <Play className="size-3.5" />
            ) : (
              <Plus className="size-icon-sm" />
            )}
          </WorkbenchIconAction>
        }
      >
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="execution-mode">Mode</Label>
            <Select value={mode} onValueChange={(value) => setMode(value as ExecutionModeValue)}>
              <SelectTrigger id="execution-mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {modeOptions.map((item) => (
                  <SelectItem key={item.value} value={item.value} disabled={!item.enabled}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-micro text-muted-foreground">
              {selectedMode?.reason ?? selectedMode?.description}
            </p>
          </div>
          <div className="grid gap-1">
            <Label>Based on execution</Label>
            <p className="break-all font-mono text-micro text-muted-foreground">
              {selectedExecution
                ? selectedExecution.executionId
                : latestExecution
                  ? `Latest execution (${latestExecution.executionId})`
                  : "This run has no attempt yet."}
            </p>
            {blockingExecutionId ? (
              <p className="text-label text-foreground">
                <span className="font-mono">{blockingExecutionId}</span> is still running. Stop it
                before starting another attempt.
              </p>
            ) : null}
          </div>
          <div className="flex items-start gap-2">
            <Checkbox
              id="bypass-cache"
              checked={mode === "reproduce" || bypassCache}
              disabled={mode === "reproduce"}
              onCheckedChange={(value) => setBypassCache(value === true)}
            />
            <div className="grid gap-1">
              <Label htmlFor="bypass-cache">Recompute everything (bypass cache)</Label>
              {mode === "reproduce" && (
                <p className="text-micro text-muted-foreground">
                  Reproduce always bypasses the cache
                </p>
              )}
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="execution-target">Target</Label>
            <Select value={target} onValueChange={setTarget}>
              <SelectTrigger id="execution-target">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {targets.length === 0 && <SelectItem value="local">local</SelectItem>}
                {targets.map((item) => (
                  <SelectItem key={item.name} value={item.name}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </AppDialog>

      {canHarvest(run.status) && onHarvested && (
        <HarvestDialog
          projectId={run.projectId}
          experimentId={run.experimentId}
          runId={run.id}
          onHarvested={onHarvested}
        />
      )}

      {selectedExecution && canCancelSelected && (
        <WorkbenchIconAction
          label={`Stop ${selectedExecution.executionId}`}
          deniedReason={writeDeniedReason}
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => void onCancel()}
        >
          <Ban className="size-icon-sm" />
        </WorkbenchIconAction>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More">
            <MoreHorizontal className="size-4" />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuItem asChild>
            <a href={runsApi.exportUrl(run.projectId, run.experimentId, run.id)} download>
              <Download className="size-icon-sm" /> Export run
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void navigator.clipboard.writeText(run.id)}>
            <Copy className="size-icon-sm" /> Copy run ID
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
