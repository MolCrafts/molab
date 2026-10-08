import { Ban, Copy, Download, MoreHorizontal, Play, Plus } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { runsApi } from "@/api";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { usePermissions } from "@/app/auth";
import {
  bypassCacheFor,
  defaultExecutionMode,
  type ExecutionModeValue,
  executionModeOptions,
} from "@/app/runs/runLifecycle";
import type { RunSummary } from "@/app/types";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";

export const POST_DISPATCH_TAB = "executions";

export interface RunToolbarProps {
  run: RunSummary;
  selectedExecutionId: string | null;
  onRefresh: () => void;
  onCancel: () => Promise<void>;
  onDispatched?: (executionId: string) => void;
}

export function RunToolbar({
  run,
  selectedExecutionId,
  onRefresh,
  onCancel,
  onDispatched,
}: RunToolbarProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const selectedExecution = run.executionHistory.find(
    (execution) => execution.executionId === selectedExecutionId,
  );
  const latestExecution = run.executionHistory[run.executionHistory.length - 1];
  const attempts = run.executionHistory.length;
  const basedOnStatus = (selectedExecution ?? latestExecution)?.status ?? null;
  const modeOptions = useMemo(
    () => executionModeOptions({ attempts, basedOnStatus }),
    [attempts, basedOnStatus],
  );
  const canCancelSelected =
    selectedExecution?.status === "queued" || selectedExecution?.status === "running";
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ExecutionModeValue>(defaultExecutionMode(modeOptions));
  const [bypassCache, setBypassCache] = useState(false);
  const [target, setTarget] = useState("local");
  const [targets, setTargets] = useState<TargetResponse[]>([]);
  const [checkpointArtifactId, setCheckpointArtifactId] = useState("");
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

  useEffect(() => {
    if (!open) return;
    setMode(defaultExecutionMode(executionModeOptions({ attempts, basedOnStatus })));
  }, [open, attempts, basedOnStatus]);

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
        ...(mode === "resume" && checkpointArtifactId ? { checkpointArtifactId } : {}),
        bypassCache: bypassCacheFor(mode, bypassCache),
        target,
        dispatch: true,
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
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setError(null);
        }}
      >
        <DialogTrigger asChild>
          <WorkbenchIconAction label="Create execution" deniedReason={writeDeniedReason}>
            {run.executionHistory.length === 0 ? (
              <Play className="size-3.5" />
            ) : (
              <Plus className="size-icon-sm" />
            )}
          </WorkbenchIconAction>
        </DialogTrigger>
        <DialogContent className="sm:max-w-dialog-sm">
          <DialogHeader>
            <DialogTitle>Create execution</DialogTitle>
            <DialogDescription>
              Run parameters and scientific inputs are immutable. This creates one new physical
              attempt.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
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
            </div>
            {mode === "resume" && (
              <div className="grid gap-2">
                <Label htmlFor="checkpoint-artifact">Checkpoint artifact ID (optional)</Label>
                <Input
                  id="checkpoint-artifact"
                  value={checkpointArtifactId}
                  onChange={(event) => setCheckpointArtifactId(event.target.value)}
                  placeholder="Artifact UUID"
                />
              </div>
            )}
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
            {error && <p className="text-label text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <WorkbenchAction
              kind="primary"
              disabled={busy || !selectedMode?.enabled}
              onClick={() => void createExecution()}
            >
              {busy ? "Creating…" : "Create"}
            </WorkbenchAction>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {canCancelSelected && (
        <WorkbenchIconAction
          label="Cancel selected execution"
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
