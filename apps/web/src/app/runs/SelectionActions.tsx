/**
 * The selection bar of a runs list (Figma L03-5): Compare first, then only the
 * verbs that apply to some of the selected runs, each with how many it touches
 * (“Resume 1”), then clear. Each verb sends one request per run; a new attempt
 * goes to the target its based-on attempt ran on.
 */

import { X } from "lucide-react";
import { type JSX, useState } from "react";
import { runsApi } from "@/api";
import { apiErrorMessage } from "@/api/errors";
import type { ExecutionAttemptCreateRequest } from "@/api/generated/models/ExecutionAttemptCreateRequest";
import type { RunSummary } from "@/app/types";
import { DialogButton } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";
import { type PlannedAttempt, planSelection, type SelectionMode } from "./selectionVerbs";

export interface SelectionActionsProps {
  runs: readonly RunSummary[];
  compareDisabledReason: string | null;
  onCompare: () => void;
  onClear: () => void;
  onChanged: () => void;
}

const applyOne = async (item: PlannedAttempt): Promise<void> => {
  if (item.mode === "cancel") {
    if (!item.executionId) return;
    await runsApi.cancelExecution(item.projectId, item.experimentId, item.runId, item.executionId);
    return;
  }
  await runsApi.createExecution(item.projectId, item.experimentId, item.runId, {
    mode: item.mode as ExecutionAttemptCreateRequest.mode,
    ...(item.executionId ? { basedOnExecutionId: item.executionId } : {}),
    ...(item.target ? { target: item.target } : {}),
  });
};

/** Apply one verb to every planned run; one notification says how it went. */
export const applyPlanned = async (
  items: readonly PlannedAttempt[],
  done: string,
): Promise<void> => {
  const failures: string[] = [];
  for (const item of items) {
    try {
      await applyOne(item);
    } catch (err) {
      failures.push(`${item.runId}: ${apiErrorMessage(err, "failed")}`);
    }
  }
  if (failures.length > 0) {
    toast.error(`${failures.length} of ${items.length} failed — ${failures[0]}`);
  } else {
    toast.success(done);
  }
};

const VERBS: readonly {
  key: "start" | "resume" | "rerun" | "cancel";
  label: string;
  mode: SelectionMode;
  past: string;
}[] = [
  { key: "resume", label: "Resume", mode: "resume", past: "resumed" },
  { key: "start", label: "Start", mode: "initial", past: "started" },
  { key: "rerun", label: "Rerun", mode: "rerun", past: "rerun" },
  { key: "cancel", label: "Cancel", mode: "cancel", past: "cancelled" },
];

export const SelectionActions = ({
  runs,
  compareDisabledReason,
  onCompare,
  onClear,
  onChanged,
}: SelectionActionsProps): JSX.Element => {
  const plan = planSelection(runs);
  const [busy, setBusy] = useState<SelectionMode | null>(null);
  const run = async (key: (typeof VERBS)[number]): Promise<void> => {
    setBusy(key.mode);
    await applyPlanned(plan[key.key], `${plan[key.key].length} ${key.past}`);
    setBusy(null);
    onChanged();
  };
  return (
    <>
      <span className="text-body font-medium text-foreground">{runs.length} selected</span>
      <span className="flex-1" />
      <DialogButton
        kind="primary"
        disabled={runs.length < 1 || compareDisabledReason !== null}
        title={compareDisabledReason ?? undefined}
        onClick={onCompare}
      >
        Compare
      </DialogButton>
      {VERBS.filter((verb) => plan[verb.key].length > 0).map((verb) => (
        <DialogButton
          key={verb.key}
          kind="secondary"
          disabled={busy !== null}
          onClick={() => void run(verb)}
        >
          {verb.label} {plan[verb.key].length}
        </DialogButton>
      ))}
      <span aria-hidden className="mx-1 h-4 w-px bg-border" />
      <WorkbenchIconAction label="Clear selection" onClick={onClear}>
        <X aria-hidden className="size-icon" />
      </WorkbenchIconAction>
    </>
  );
};
