/**
 * Which lifecycle verb applies to each selected run.
 *
 * A run can appear under more than one verb: a failed attempt can be resumed
 * or rerun. The bar shows both counts and the user picks one verb.
 */

import { attemptTarget } from "@/app/renderers/run/runStory";
import type { RunSummary } from "@/app/types";
import { canCancel, canRerun, canResume, canStart } from "./runLifecycle";

export type SelectionMode = "initial" | "resume" | "rerun" | "cancel";

export interface PlannedAttempt {
  runId: string;
  projectId: string;
  experimentId: string;
  /** Set for cancel, resume, and rerun. Absent for the first attempt. */
  executionId: string | null;
  mode: SelectionMode;
  /** Where the based-on attempt ran: a new attempt goes there too. Null lets the server choose. */
  target: string | null;
}

export interface SelectionPlan {
  start: PlannedAttempt[];
  cancel: PlannedAttempt[];
  resume: PlannedAttempt[];
  rerun: PlannedAttempt[];
}

const attempt = (
  run: RunSummary,
  mode: SelectionMode,
  executionId: string | null,
): PlannedAttempt => {
  const based = run.executionHistory.find((execution) => execution.executionId === executionId);
  return {
    runId: run.id,
    projectId: run.projectId,
    experimentId: run.experimentId,
    executionId,
    mode,
    target: attemptTarget(based),
  };
};

export const planSelection = (runs: readonly RunSummary[]): SelectionPlan => {
  const plan: SelectionPlan = { start: [], cancel: [], resume: [], rerun: [] };
  for (const run of runs) {
    const history = run.executionHistory;
    const latest = history.length > 0 ? history[history.length - 1] : null;
    const live = history.find((execution) => canCancel(execution.status));
    if (canStart(run.status) && history.length === 0) {
      plan.start.push(attempt(run, "initial", null));
    }
    if (live) plan.cancel.push(attempt(run, "cancel", live.executionId));
    if (latest && canResume(latest.status)) {
      plan.resume.push(attempt(run, "resume", latest.executionId));
    }
    if (latest && canRerun(latest.status)) {
      plan.rerun.push(attempt(run, "rerun", latest.executionId));
    }
  }
  return plan;
};
