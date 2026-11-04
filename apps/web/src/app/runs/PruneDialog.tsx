/**
 * Review, then remove, the bulk directories of sealed attempts.
 *
 * Plan and apply are the same endpoint. Apply is enabled only after a plan
 * comes back with something to delete.
 */

import {
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@molcrafts/ui";
import { Trash2 } from "lucide-react";
import { type JSX, useState } from "react";
import { runsApi } from "@/api";
import { apiErrorMessage } from "@/api/errors";
import type { RunPruneResponse } from "@/api/generated/models/RunPruneResponse";
import { TERMINAL_STATUSES } from "@/app/runs/runLifecycle";
import type { RunSummary } from "@/app/types";
import { toast } from "@/components/ui/toast";
import { WorkbenchAction } from "@/components/workbench";

export interface PruneDialogProps {
  run: RunSummary;
  onPruned?: () => void;
}

export const PruneDialog = ({ run, onPruned }: PruneDialogProps): JSX.Element => {
  const terminal = run.executionHistory.filter((execution) =>
    TERMINAL_STATUSES.has(execution.status.toLowerCase()),
  );
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>(() =>
    terminal.map((item) => item.executionId),
  );
  const [plan, setPlan] = useState<RunPruneResponse | null>(null);
  const [busy, setBusy] = useState<"plan" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = (next: boolean): void => {
    if (next) {
      setSelected(terminal.map((item) => item.executionId));
      setPlan(null);
      setError(null);
    }
    setOpen(next);
  };

  const review = async (): Promise<void> => {
    setBusy("plan");
    setError(null);
    setPlan(null);
    try {
      setPlan(
        await runsApi.prune(run.projectId, run.experimentId, run.id, {
          executionIds: selected,
          apply: false,
        }),
      );
    } catch (err) {
      setError(apiErrorMessage(err, "Could not plan the prune."));
    } finally {
      setBusy(null);
    }
  };

  const apply = async (): Promise<void> => {
    setBusy("apply");
    setError(null);
    try {
      const applied = await runsApi.prune(run.projectId, run.experimentId, run.id, {
        executionIds: selected,
        apply: true,
      });
      toast.success(`${applied.removed ?? 0} directories removed`);
      setOpen(false);
      onPruned?.();
    } catch (err) {
      setError(apiErrorMessage(err, "Could not prune."));
    } finally {
      setBusy(null);
    }
  };

  const removable = plan?.entries.reduce((count, entry) => count + entry.dirs.length, 0) ?? 0;

  return (
    <>
      <WorkbenchAction
        icon={<Trash2 aria-hidden />}
        kind="ghost"
        size="content"
        type="button"
        disabled={terminal.length === 0}
        deniedReason={terminal.length === 0 ? "No sealed attempt to prune." : null}
        onClick={() => reset(true)}
      >
        Prune
      </WorkbenchAction>
      <Dialog open={open} onOpenChange={reset}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Prune bulk</DialogTitle>
            <DialogDescription>
              Removes out, work, jobs, and checkpoints. The attempt record stays.
            </DialogDescription>
          </DialogHeader>
          <ul className="grid gap-2">
            {terminal.map((execution) => {
              const checked = selected.includes(execution.executionId);
              return (
                <li key={execution.executionId} className="flex items-center gap-2">
                  <Checkbox
                    id={`prune-${execution.executionId}`}
                    checked={checked}
                    onCheckedChange={(value) => {
                      setPlan(null);
                      setSelected((current) =>
                        value
                          ? [...current, execution.executionId]
                          : current.filter((id) => id !== execution.executionId),
                      );
                    }}
                  />
                  <label htmlFor={`prune-${execution.executionId}`} className="text-body">
                    <span className="font-mono">{execution.executionId}</span>
                    <span className="text-muted-foreground"> {execution.status}</span>
                  </label>
                </li>
              );
            })}
          </ul>
          {plan ? (
            <ul className="grid gap-1 text-label text-muted-foreground">
              {plan.entries.map((entry) => (
                <li key={entry.executionId}>
                  <span className="font-mono text-foreground">{entry.executionId}</span>
                  {entry.dirs.length > 0 ? ` ${entry.dirs.join(", ")}` : " nothing to remove"}
                </li>
              ))}
            </ul>
          ) : null}
          {error ? <p className="text-body text-destructive">{error}</p> : null}
          <DialogFooter>
            <WorkbenchAction
              kind="secondary"
              size="default"
              disabled={busy !== null || selected.length === 0}
              onClick={() => void review()}
            >
              {busy === "plan" ? "Reviewing…" : "Review"}
            </WorkbenchAction>
            <WorkbenchAction
              icon={<Trash2 aria-hidden />}
              kind="primary"
              size="default"
              disabled={busy !== null || removable === 0}
              onClick={() => void apply()}
            >
              {busy === "apply" ? "Removing…" : "Remove bulk"}
            </WorkbenchAction>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};
