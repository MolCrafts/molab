/**
 * A run's editor actions (Figma L04, decision 3): the state's one primary
 * action at the right of the editor tab row, then ⋯.
 *   failed · interrupted · cancelled → Resume (New attempt, Resume chosen)
 *   queued · running · finalizing    → Stop eNN
 *   succeeded                        → Compare (pin to the compare set)
 *   not started                      → Start
 * ⋯ holds New attempt…, Rerun from scratch, Harvest…, Export, Compare with…,
 * Copy run id, Copy definition hash. ⌥R New attempt · ⌥⇧R Rerun from scratch.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { MoreHorizontal } from "lucide-react";
import { type JSX, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { runsApi } from "@/api";
import { usePermissions } from "@/app/auth";
import { itemKey } from "@/app/compare/types";
import { useCompareSet } from "@/app/compare/useCompareSet";
import { HarvestDialog } from "@/app/components/HarvestDialog";
import { NewAttemptDialog, type NewAttemptRequest } from "@/app/runs/NewAttemptDialog";
import { canCancel, canHarvest, canResume } from "@/app/runs/runLifecycle";
import { shortcut } from "@/app/shell/keys";
import { normalizeStatus } from "@/app/status/vocabulary";
import type { ExecutionRecordSummary, RunSummary } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";

type CompareEntry = Parameters<ReturnType<typeof useCompareSet>["add"]>[0];

export interface RunEditorActionsProps {
  run: RunSummary;
  /** The attempt the page shows: the default base of a new attempt. */
  pageExecutionId: string | null;
  /** This run as a compare-set entry; null when it cannot be compared here. */
  compareEntry: CompareEntry | null;
  /** Stop one active attempt (confirms first). */
  onStop: (execution: ExecutionRecordSummary) => void;
  /** A new attempt was created: the page follows it. */
  onCreated: (executionId: string) => void;
  onOpenLogs: () => void;
  onHarvested: (path: string) => void;
  /** An outside request to open New attempt (a Preview's Resume, `?new=resume`). */
  request: NewAttemptRequest | null;
  onRequestHandled: () => void;
}

/** ⌥ + key, without ⌘ / Ctrl, outside a text field. */
const altKey = (event: KeyboardEvent, key: string, shift = false): boolean => {
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, textarea, [contenteditable='true']")) return false;
  return (
    event.altKey &&
    !event.metaKey &&
    !event.ctrlKey &&
    event.shiftKey === shift &&
    event.code === `Key${key}`
  );
};

export function RunEditorActions({
  run,
  pageExecutionId,
  compareEntry,
  onStop,
  onCreated,
  onOpenLogs,
  onHarvested,
  request,
  onRequestHandled,
}: RunEditorActionsProps): JSX.Element {
  const { writeDeniedReason } = usePermissions();
  const compare = useCompareSet();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<NewAttemptRequest | null>(null);
  const [harvesting, setHarvesting] = useState(false);
  const history = run.executionHistory;
  const latest = history.at(-1) ?? null;
  const status = latest ? normalizeStatus(latest.status) : "pending";
  const active = [...history].reverse().find((execution) => canCancel(execution.status)) ?? null;
  const pinned = compareEntry ? compare.has(itemKey(compareEntry.ref)) : false;
  const canWrite = !writeDeniedReason;

  const openDialog = (next: NewAttemptRequest): void => {
    if (canWrite) setDialog(next);
  };

  useEffect(() => {
    if (!request) return;
    onRequestHandled();
    if (canWrite && !dialog) setDialog(request);
  }, [request, onRequestHandled, canWrite, dialog]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (altKey(event, "R", true)) {
        event.preventDefault();
        openDialog({ mode: "rerun", bypassCache: true });
      } else if (altKey(event, "R")) {
        event.preventDefault();
        openDialog({ mode: canResume(latest?.status ?? "") ? "resume" : "rerun" });
      } else if (altKey(event, "L")) {
        event.preventDefault();
        onOpenLogs();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const toggleCompare = (): void => {
    if (!compareEntry) return;
    if (pinned) compare.remove(itemKey(compareEntry.ref));
    else compare.add(compareEntry);
  };

  const primary =
    status === "pending" ? (
      <DialogButton
        size="chrome"
        kind="primary"
        disabled={!canWrite}
        title={writeDeniedReason ?? undefined}
        onClick={() => openDialog({ mode: "initial" })}
      >
        Start
      </DialogButton>
    ) : active ? (
      <DialogButton
        size="chrome"
        kind="secondary"
        disabled={!canWrite}
        title={writeDeniedReason ?? undefined}
        onClick={() => onStop(active)}
      >
        Stop {active.executionId}
      </DialogButton>
    ) : canResume(status) ? (
      <DialogButton
        size="chrome"
        kind="primary"
        disabled={!canWrite}
        title={writeDeniedReason ?? `New attempt, Resume (${shortcut({ alt: true, key: "R" })})`}
        onClick={() => openDialog({ mode: "resume" })}
      >
        Resume
      </DialogButton>
    ) : status === "succeeded" && compareEntry ? (
      <DialogButton size="chrome" kind="secondary" aria-pressed={pinned} onClick={toggleCompare}>
        {pinned ? "Unpin" : "Compare"}
      </DialogButton>
    ) : null;

  return (
    <div className="flex items-center gap-1">
      {primary}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction label="More actions">
            <MoreHorizontal className="size-icon" />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuItem
            disabled={!canWrite}
            onSelect={() => openDialog({ mode: canResume(status) ? "resume" : "rerun" })}
          >
            New attempt…
            <DropdownMenuShortcut>{shortcut({ alt: true, key: "R" })}</DropdownMenuShortcut>
          </DropdownMenuItem>
          <DropdownMenuItem
            disabled={!canWrite || history.length === 0}
            onSelect={() => openDialog({ mode: "rerun", bypassCache: true })}
          >
            Rerun from scratch…
            <DropdownMenuShortcut>
              {shortcut({ alt: true, shift: true, key: "R" })}
            </DropdownMenuShortcut>
          </DropdownMenuItem>
          {canHarvest(status) ? (
            <DropdownMenuItem disabled={!canWrite} onSelect={() => setHarvesting(true)}>
              Harvest…
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuSeparator />
          {compareEntry ? (
            <DropdownMenuItem
              onSelect={() => {
                if (!pinned) compare.add(compareEntry);
                navigate("/compare");
              }}
            >
              Compare with…
            </DropdownMenuItem>
          ) : null}
          <DropdownMenuItem asChild>
            <a href={runsApi.exportUrl(run.projectId, run.experimentId, run.id)} download>
              Export
            </a>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => {
              void navigator.clipboard.writeText(run.id);
              toast("Copied run id");
            }}
          >
            Copy run id
          </DropdownMenuItem>
          {run.definitionHash ? (
            <DropdownMenuItem
              onSelect={() => {
                void navigator.clipboard.writeText(run.definitionHash);
                toast("Copied definition hash");
              }}
            >
              Copy definition hash
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      <NewAttemptDialog
        run={run}
        open={dialog !== null}
        onOpenChange={(next) => {
          if (!next) setDialog(null);
        }}
        request={dialog}
        pageExecutionId={pageExecutionId}
        onCreated={({ id, target }) => {
          toast.success(`Attempt ${id} created and queued on ${target}.`, {
            action: { label: "Open logs", onClick: onOpenLogs },
          });
          onCreated(id);
        }}
      />
      {harvesting ? (
        <HarvestDialog
          projectId={run.projectId}
          experimentId={run.experimentId}
          runId={run.id}
          trigger={null}
          open
          onOpenChange={setHarvesting}
          onHarvested={(path) => {
            setHarvesting(false);
            onHarvested(path);
          }}
        />
      ) : null}
    </div>
  );
}
