/**
 * Pure reads and edits of a Delegation record for `<molab-approval>`
 * (`src/molab/knowledge/delegation.py`). Edits return a new record that keeps
 * every other key.
 */

export type DelegationRecord = Readonly<Record<string, unknown>>;

export const APPROVAL_GATES = ["parameters", "plan", "dry_run", "results"] as const;
export type ApprovalGate = (typeof APPROVAL_GATES)[number];

export interface Approval {
  gate: string;
  target: string;
  by: string;
  at: string;
  note?: string;
}

const text = (value: unknown): string => (typeof value === "string" ? value.trim() : "");

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const isApprovalGate = (value: string): value is ApprovalGate =>
  (APPROVAL_GATES as readonly string[]).includes(value);

/** A record that names a goal or a scope is a delegation. */
export const isDelegationRecord = (record: DelegationRecord): boolean =>
  Boolean(text(record.goal) || text(record.scope));

export const delegationState = (record: DelegationRecord): string => text(record.state) || "open";

/** What is asked: the explicit ask, else the last question, the plan, the goal. */
export const delegationAsk = (record: DelegationRecord, ask?: string): string => {
  if (ask?.trim()) return ask.trim();
  const questions = Array.isArray(record.questions) ? record.questions.map(text) : [];
  const last = questions.filter(Boolean).at(-1);
  return last ?? (text(record.current_plan) || text(record.goal));
};

export const readApprovals = (record: DelegationRecord): Approval[] =>
  (Array.isArray(record.approvals) ? record.approvals : []).flatMap((row) => {
    if (!isObject(row)) return [];
    const approval: Approval = {
      gate: text(row.gate),
      target: text(row.target),
      by: text(row.by),
      at: text(row.at),
    };
    const note = text(row.note);
    return [note ? { ...approval, note } : approval];
  });

/** The latest approval of *gate* on *target*, if any. */
export const findApproval = (
  record: DelegationRecord,
  gate: string,
  target: string,
): Approval | null =>
  readApprovals(record)
    .filter((row) => row.gate === gate && row.target === target)
    .at(-1) ?? null;

/** Append an approval and release the delegation (`state: open`). */
export const withApproval = (
  record: DelegationRecord,
  approval: Approval,
): Record<string, unknown> => ({
  ...record,
  approvals: [...(Array.isArray(record.approvals) ? record.approvals : []), approval],
  state: "open",
});

/** A person holds the delegation: `state: paused`. */
export const withRejection = (record: DelegationRecord): Record<string, unknown> => ({
  ...record,
  state: "paused",
});

/** Whether the ask still needs a decision: blocked, or an explicit gate not yet approved. */
export const needsDecision = (
  record: DelegationRecord,
  gate: string | undefined,
  target: string,
): boolean => {
  const state = delegationState(record);
  if (state === "paused" || state === "done" || state === "stopped") return false;
  if (gate) return findApproval(record, gate, target) === null;
  return state === "blocked";
};
