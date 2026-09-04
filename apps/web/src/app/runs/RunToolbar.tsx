import { Ban, Bot, Copy, Download, MoreHorizontal, Play, Plus } from "lucide-react";
import { type JSX, useEffect, useMemo, useState } from "react";
import { runsApi } from "@/api";
import { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { TargetResponse } from "@/api/generated/models/TargetResponse";
import { TargetsService } from "@/api/generated/services/TargetsService";
import { usePermissions } from "@/app/auth";
import type { RunSummary } from "@/app/types";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";

export const POST_DISPATCH_TAB = "executions";

type ExecutionMode = ExecutionAttemptCreateRequest.mode;

const modes: Array<{ value: ExecutionMode; label: string; description: string }> = [
  { value: ExecutionAttemptCreateRequest.mode.INITIAL, label: "Initial", description: "Create an independent first realization." },
  { value: ExecutionAttemptCreateRequest.mode.RETRY, label: "Retry", description: "Retry the selected execution after an operational failure." },
  { value: ExecutionAttemptCreateRequest.mode.RERUN, label: "Rerun", description: "Run the same scientific definition again." },
  { value: ExecutionAttemptCreateRequest.mode.RESUME, label: "Resume", description: "Continue from an explicitly selected checkpoint artifact." },
  { value: ExecutionAttemptCreateRequest.mode.REPRODUCE, label: "Reproduce", description: "Create a reproducibility verification execution." },
];

export interface RunToolbarProps {
  run: RunSummary;
  selectedExecutionId: string | null;
  onRefresh: () => void;
  onCancel: () => Promise<void>;
  onDispatched?: (executionId: string) => void;
  onOpenAgent: () => void;
}

export function RunToolbar({
  run, selectedExecutionId, onRefresh, onCancel, onDispatched, onOpenAgent,
}: RunToolbarProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const selectedExecution = run.executionHistory.find(
    (execution) => execution.executionId === selectedExecutionId,
  );
  const canCancelSelected =
    selectedExecution?.status === "queued" || selectedExecution?.status === "running";
  const defaultMode = run.executionHistory.length === 0
    ? ExecutionAttemptCreateRequest.mode.INITIAL
    : ExecutionAttemptCreateRequest.mode.RERUN;
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<ExecutionMode>(defaultMode);
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
      .catch(() => { if (!cancelled) setTargets([]); });
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => { if (open) setMode(defaultMode); }, [defaultMode, open]);

  const requiresParent = mode !== ExecutionAttemptCreateRequest.mode.INITIAL;
  const invalid = requiresParent && !selectedExecutionId;
  const selectedMode = useMemo(() => modes.find((item) => item.value === mode), [mode]);

  const createExecution = async (): Promise<void> => {
    if (invalid) return;
    setBusy(true);
    setError(null);
    try {
      const execution = await runsApi.createExecution(run.projectId, run.experimentId, run.id, {
        mode,
        basedOnExecutionId: requiresParent ? selectedExecutionId : null,
        checkpointArtifactId: mode === ExecutionAttemptCreateRequest.mode.RESUME ? checkpointArtifactId || null : null,
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
      <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) setError(null); }}>
        <DialogTrigger asChild>
          <WorkbenchIconAction label="Create execution" deniedReason={writeDeniedReason}>
            {run.executionHistory.length === 0
              ? <Play className="h-3.5 w-3.5" />
              : <Plus className="h-3.5 w-3.5" />}
          </WorkbenchIconAction>
        </DialogTrigger>
        <DialogContent className="sm:max-w-dialog-sm">
          <DialogHeader>
            <DialogTitle>Create execution</DialogTitle>
            <DialogDescription>
              Run parameters and scientific inputs are immutable. This creates one new physical attempt.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="execution-mode">Mode</Label>
              <Select value={mode} onValueChange={(value) => setMode(value as ExecutionMode)}>
                <SelectTrigger id="execution-mode"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {modes.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-micro text-muted-foreground">{selectedMode?.description}</p>
            </div>
            {requiresParent && (
              <div className="grid gap-1">
                <Label>Based on execution</Label>
                <p className="break-all font-mono text-micro text-muted-foreground">
                  {selectedExecutionId ?? "Select an execution in the Executions tab first."}
                </p>
              </div>
            )}
            {mode === ExecutionAttemptCreateRequest.mode.RESUME && (
              <div className="grid gap-2">
                <Label htmlFor="checkpoint-artifact">Checkpoint artifact ID</Label>
                <Input id="checkpoint-artifact" value={checkpointArtifactId}
                  onChange={(event) => setCheckpointArtifactId(event.target.value)} placeholder="Artifact UUID" />
              </div>
            )}
            <div className="grid gap-2">
              <Label htmlFor="execution-target">Target</Label>
              <Select value={target} onValueChange={setTarget}>
                <SelectTrigger id="execution-target"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {targets.length === 0 && <SelectItem value="local">local</SelectItem>}
                  {targets.map((item) => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {error && <p className="text-label text-destructive">{error}</p>}
          </div>
          <DialogFooter>
            <WorkbenchAction kind="primary"
              disabled={busy || invalid || (mode === ExecutionAttemptCreateRequest.mode.RESUME && !checkpointArtifactId)}
              onClick={() => void createExecution()}>
              {busy ? "Creating…" : "Create"}
            </WorkbenchAction>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {canCancelSelected && (
        <WorkbenchIconAction label="Cancel selected execution" deniedReason={writeDeniedReason}
          className="text-destructive hover:bg-destructive/10 hover:text-destructive"
          onClick={() => void onCancel()}>
          <Ban className="h-3.5 w-3.5" />
        </WorkbenchIconAction>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More"><MoreHorizontal className="h-4 w-4" /></WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuItem asChild>
            <a href={runsApi.exportUrl(run.projectId, run.experimentId, run.id)} download>
              <Download className="h-3.5 w-3.5" /> Export run
            </a>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void navigator.clipboard.writeText(run.id)}>
            <Copy className="h-3.5 w-3.5" /> Copy run ID
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={onOpenAgent}>
            <Bot className="h-3.5 w-3.5" /> Open agent
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
