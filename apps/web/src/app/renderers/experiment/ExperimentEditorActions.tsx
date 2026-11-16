/**
 * An experiment's editor actions (Figma L03-2, decision 3): the state's one
 * primary action, then ⋯.
 *   runs need attention                → Resume n (one confirm listing them)
 *   nothing run, a space declared      → Sweep n
 *   otherwise                          → New run (secondary while runs are going)
 * ⋯ holds New run…, Sweep…, Compare all, Copy experiment id, Delete…
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { MoreHorizontal } from "lucide-react";
import { type JSX, useState } from "react";
import { usePermissions } from "@/app/auth";
import { declaredCellCount, experimentVerdict } from "@/app/renderers/experiment/experimentStory";
import { runLabel } from "@/app/runs/runTitle";
import { applyPlanned } from "@/app/runs/SelectionActions";
import { planSelection } from "@/app/runs/selectionVerbs";
import type { ExperimentSummary, RunSummary } from "@/app/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { DialogButton } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";

export interface ExperimentEditorActionsProps {
  experiment: ExperimentSummary;
  runs: readonly RunSummary[];
  onNewRun: () => void;
  onSweep: () => void;
  onCompareAll: (() => void) | null;
  onDelete: () => void;
  onChanged: () => void;
}

/** Listed in the Resume confirm before the rest are counted. */
const MAX_LISTED = 8;

export function ExperimentEditorActions({
  experiment,
  runs,
  onNewRun,
  onSweep,
  onCompareAll,
  onDelete,
  onChanged,
}: ExperimentEditorActionsProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const { confirm, dialog } = useConfirm();
  const [busy, setBusy] = useState(false);
  const canWrite = !writeDeniedReason;
  const verdict = experimentVerdict(
    runs.map((run) => ({ id: run.id, status: run.status, parameters: run.parameters })),
  );
  const cells = declaredCellCount(experiment.parameterSpace);
  const attentionRuns = runs.filter((run) => verdict.attention.includes(run.id));
  const resumable = planSelection(attentionRuns).resume;

  const resumeAll = async (): Promise<void> => {
    const listed = attentionRuns.slice(0, MAX_LISTED).map((run) => runLabel(run));
    const more = attentionRuns.length - listed.length;
    const ok = await confirm({
      title: `Resume ${resumable.length} ${resumable.length === 1 ? "run" : "runs"}?`,
      description: (
        <span className="block space-y-1">
          <span className="block">
            Each resumes from its latest attempt, on the target it ran on.
          </span>
          <span className="block font-mono text-label">
            {listed.join(" · ")}
            {more > 0 ? ` · +${more}` : ""}
          </span>
        </span>
      ),
      confirmLabel: `Resume ${resumable.length}`,
    });
    if (!ok) return;
    setBusy(true);
    await applyPlanned(resumable, `${resumable.length} resumed`);
    setBusy(false);
    onChanged();
  };

  const primary =
    resumable.length > 0 ? (
      <DialogButton
        size="chrome"
        kind="primary"
        disabled={!canWrite || busy}
        title={writeDeniedReason ?? undefined}
        onClick={() => void resumeAll()}
      >
        Resume {resumable.length}
      </DialogButton>
    ) : runs.length === 0 && cells > 0 ? (
      <DialogButton
        size="chrome"
        kind="primary"
        disabled={!canWrite}
        title={writeDeniedReason ?? undefined}
        onClick={onSweep}
      >
        Sweep {cells}
      </DialogButton>
    ) : (
      <DialogButton
        size="chrome"
        kind={verdict.state === "active" ? "secondary" : "primary"}
        disabled={!canWrite}
        title={writeDeniedReason ?? undefined}
        onClick={onNewRun}
      >
        New run
      </DialogButton>
    );

  return (
    <div className="flex items-center gap-1">
      {primary}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal className="size-icon" />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuItem disabled={!canWrite} onSelect={onNewRun}>
            New run…
          </DropdownMenuItem>
          <DropdownMenuItem disabled={!canWrite} onSelect={onSweep}>
            Sweep…
          </DropdownMenuItem>
          {onCompareAll ? (
            <DropdownMenuItem disabled={runs.length === 0} onSelect={onCompareAll}>
              Compare all runs
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => {
              void navigator.clipboard.writeText(experiment.id);
              toast("Copied experiment id");
            }}
          >
            Copy experiment id
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={!canWrite}
            className="text-destructive focus:text-destructive"
            onSelect={onDelete}
          >
            Delete…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {dialog}
    </div>
  );
}
