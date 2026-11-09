/**
 * `<molab-approval>` (L10, Figma v2_02): a delegation's ask — what the agent
 * wants to do, the scope it works in — and, while it waits on a person,
 * Approve / Reject. Approve records who approved which gate and releases the
 * delegation; Reject holds it (paused). Afterwards the row says who and when.
 */

import { Bot } from "lucide-react";
import type { JSX } from "react";
import { useAuth } from "@/app/auth";
import { StatusIcon } from "@/app/components/entity";
import { DialogButton } from "@/components/dialog/AppDialog";
import { formatRelative } from "@/lib/format-time";
import { type DocComponentProps, type DocComponentSpec, useDoc } from "../context";
import { ComponentFrame, ComponentLoading, ComponentNotice } from "../frame";
import {
  type Approval as ApprovalRow,
  delegationAsk,
  delegationState,
  findApproval,
  isApprovalGate,
  isDelegationRecord,
  needsDecision,
  withApproval,
  withRejection,
} from "./delegationEdits";
import { useRecordSource } from "./useRecordSource";

const NAME = "molab-approval";

const Outcome = ({ approval, state }: { approval: ApprovalRow | null; state: string }) => {
  if (approval) {
    return (
      <p className="flex items-center gap-2 text-label text-muted-foreground">
        <StatusIcon status="succeeded" />
        <span title={approval.at}>
          Approved by {approval.by || "someone"} · {formatRelative(approval.at || null)}
          {approval.note ? ` · ${approval.note}` : ""}
        </span>
      </p>
    );
  }
  if (state === "paused") {
    return (
      <p className="flex items-center gap-2 text-label text-muted-foreground">
        <StatusIcon status="cancelled" />
        <span>Held by a person</span>
      </p>
    );
  }
  return null;
};

export const Approval = ({ attrs }: DocComponentProps): JSX.Element => {
  const doc = useDoc();
  const { user } = useAuth();
  const source = useRecordSource(attrs.src);
  if (source.state === "loading") return <ComponentLoading name={NAME} />;
  if (source.state === "missing")
    return <ComponentNotice name={NAME}>{source.message}</ComponentNotice>;
  const { record } = source;
  if ((!attrs.src && source.cls !== "Delegation") || !isDelegationRecord(record)) {
    return (
      <ComponentNotice name={NAME}>Set src to the path of a Delegation document.</ComponentNotice>
    );
  }
  const gate = attrs.gate?.trim() || undefined;
  if (gate && !isApprovalGate(gate)) {
    return (
      <ComponentNotice name={NAME}>
        gate must be parameters, plan, dry_run or results.
      </ComponentNotice>
    );
  }
  const target = attrs.target?.trim() || doc.relPath;
  const state = delegationState(record);
  const deciding = needsDecision(record, gate, target);
  const approve = (): void =>
    source.commit(
      withApproval(record, {
        gate: gate ?? "plan",
        target,
        by: user?.username ?? "you",
        at: new Date().toISOString(),
      }),
    );
  const scope = typeof record.scope === "string" ? record.scope : "";
  return (
    <ComponentFrame label="Approval">
      <div className="space-y-2 px-3 py-3">
        <p className="flex items-start gap-2 text-body text-foreground">
          <Bot aria-hidden className="mt-hairline size-icon flex-none text-muted-foreground" />
          <span className="min-w-0">{delegationAsk(record, attrs.ask)}</span>
        </p>
        {scope ? <p className="pl-6 text-label text-muted-foreground">{scope}</p> : null}
        <div className="pl-6">
          {deciding ? (
            <div className="flex gap-2">
              <DialogButton
                kind="primary"
                size="chrome"
                type="button"
                disabled={!source.writable}
                onClick={approve}
              >
                Approve
              </DialogButton>
              <DialogButton
                kind="secondary"
                size="chrome"
                type="button"
                disabled={!source.writable}
                onClick={() => source.commit(withRejection(record))}
              >
                Reject
              </DialogButton>
            </div>
          ) : (
            <Outcome approval={findApproval(record, gate ?? "plan", target)} state={state} />
          )}
          {source.error ? (
            <p role="alert" className="mt-2 text-label text-status-failed-foreground">
              {source.error}
            </p>
          ) : null}
        </div>
      </div>
    </ComponentFrame>
  );
};

export const approvalSpec: DocComponentSpec = {
  name: NAME,
  label: "Approval",
  description: "A delegation's ask: Approve or Reject, then who decided.",
  keywords: ["approval", "approve", "delegation", "agent", "gate"],
  icon: Bot,
  template: {},
  Component: Approval,
};
