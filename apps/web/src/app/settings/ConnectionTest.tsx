/**
 * A connection test's outcome (L11), shared by remote workspaces and compute
 * targets: a status line for the setting's description, and the checks,
 * listed under its buttons. A test is not persisted, so the status is this
 * session's test or "not tested".
 */

import { Check, CircleCheck, CircleDot, CircleX, X } from "lucide-react";
import type { JSX } from "react";
import type { TargetTestResponse } from "@/api/generated/models/TargetTestResponse";

export interface TestOutcome {
  result: TargetTestResponse;
  at: number;
}

const ago = (at: number): string => {
  const seconds = Math.round((Date.now() - at) / 1000);
  if (seconds < 60) return "tested now";
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `tested ${minutes} min ago` : `tested ${Math.round(minutes / 60)} h ago`;
};

export const TestStatus = ({ outcome }: { outcome: TestOutcome | null }): JSX.Element => {
  if (!outcome)
    return (
      <span className="inline-flex items-center gap-1">
        <CircleDot aria-hidden className="size-icon-sm text-muted-foreground" />
        not tested
      </span>
    );
  const { ok } = outcome.result;
  const Icon = ok ? CircleCheck : CircleX;
  return (
    <span className="inline-flex items-center gap-1">
      <Icon
        aria-hidden
        className={
          ok
            ? "size-icon-sm text-status-completed-foreground"
            : "size-icon-sm text-status-failed-foreground"
        }
      />
      {ok ? "reachable" : "unreachable"}, {ago(outcome.at)}
    </span>
  );
};

export const TestChecks = ({ outcome }: { outcome: TestOutcome | null }): JSX.Element | null => {
  if (!outcome) return null;
  const { checks, error } = outcome.result;
  return (
    <ul aria-label="Test checks" className="flex flex-col gap-1 text-label">
      {checks.map((check) => (
        <li key={check.label} className="flex items-start gap-2">
          {check.ok ? (
            <Check
              aria-hidden
              className="mt-hairline size-icon-sm flex-none text-status-completed-foreground"
            />
          ) : (
            <X
              aria-hidden
              className="mt-hairline size-icon-sm flex-none text-status-failed-foreground"
            />
          )}
          <span>
            {check.label}
            {check.detail ? <span className="text-muted-foreground"> — {check.detail}</span> : null}
          </span>
        </li>
      ))}
      {error ? <li className="text-status-failed-foreground">{error}</li> : null}
    </ul>
  );
};
