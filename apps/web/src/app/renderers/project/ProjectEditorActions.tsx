/**
 * A project's editor actions (Figma L02-2, L02-7, decisions 3 and 7): New
 * experiment — secondary while runs are going — then ⋯ with New experiment…,
 * Open runs, Compare all runs, Copy project id and Delete project…. Delete asks
 * for the project's name: it removes the experiments, the runs and their files.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
} from "@molcrafts/ui";
import { MoreHorizontal } from "lucide-react";
import { type JSX, useState } from "react";
import { usePermissions } from "@/app/auth";
import { AppDialog, DialogButton } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";

export interface ProjectEditorActionsProps {
  projectId: string;
  projectName: string;
  experimentCount: number;
  runCount: number;
  /** Runs are going: New experiment steps back to secondary. */
  active: boolean;
  onNewExperiment: () => void;
  onOpenRuns: () => void;
  onCompareAll: (() => void) | null;
  onDelete: () => Promise<void>;
}

const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? "" : "s"}`;

const DeleteProjectDialog = ({
  open,
  onOpenChange,
  projectName,
  experimentCount,
  runCount,
  onDelete,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectName: string;
  experimentCount: number;
  runCount: number;
  onDelete: () => Promise<void>;
}): JSX.Element => {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const close = (next: boolean): void => {
    if (!next) {
      setTyped("");
      setError(null);
    }
    onOpenChange(next);
  };
  return (
    <AppDialog
      open={open}
      onOpenChange={close}
      size="confirm"
      danger
      title="Delete project"
      message={
        <>
          Deletes <b>{projectName}</b>, its {plural(experimentCount, "experiment")} and{" "}
          {plural(runCount, "run")}, and their files. The workspace history (git) keeps the record.
        </>
      }
      primaryLabel="Delete project"
      primaryDisabled={typed.trim() !== projectName}
      busy={busy}
      busyLabel="Deleting…"
      error={error}
      onPrimary={async () => {
        setBusy(true);
        setError(null);
        try {
          await onDelete();
          close(false);
        } catch (failure) {
          setError(failure instanceof Error ? failure.message : "Could not delete the project");
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="grid gap-2">
        <Label htmlFor="delete-project-name">Type the project name to confirm</Label>
        <Input
          id="delete-project-name"
          autoComplete="off"
          value={typed}
          placeholder={projectName}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>
    </AppDialog>
  );
};

export function ProjectEditorActions({
  projectId,
  projectName,
  experimentCount,
  runCount,
  active,
  onNewExperiment,
  onOpenRuns,
  onCompareAll,
  onDelete,
}: ProjectEditorActionsProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const canWrite = !writeDeniedReason;
  const [deleteOpen, setDeleteOpen] = useState(false);
  return (
    <div className="flex items-center gap-1">
      <DialogButton
        size="chrome"
        kind={active ? "secondary" : "primary"}
        disabled={!canWrite}
        title={writeDeniedReason ?? undefined}
        onClick={onNewExperiment}
      >
        New experiment
      </DialogButton>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal className="size-icon" />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuItem disabled={!canWrite} onSelect={onNewExperiment}>
            New experiment…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={onOpenRuns}>Open runs</DropdownMenuItem>
          {onCompareAll ? (
            <DropdownMenuItem disabled={runCount === 0} onSelect={onCompareAll}>
              Compare all runs
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => {
              void navigator.clipboard.writeText(projectId);
              toast("Copied project id");
            }}
          >
            Copy project id
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={!canWrite}
            className="text-destructive focus:text-destructive"
            onSelect={() => setDeleteOpen(true)}
          >
            Delete project…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DeleteProjectDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        projectName={projectName}
        experimentCount={experimentCount}
        runCount={runCount}
        onDelete={onDelete}
      />
    </div>
  );
}
