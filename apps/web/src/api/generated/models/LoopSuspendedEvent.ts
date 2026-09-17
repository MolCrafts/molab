/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Terminal event — the emergent outer loop parked itself durably.
 *
 * The dual of :class:`LoopCompletedEvent` for the suspend branch: a
 * :class:`~molab.harness.agent.loops.hooks.ShouldStopGuard` returned
 * :meth:`~molab.harness.agent.loops.hooks.HookOutcome.suspend`, so
 * the ReAct turn stops without a completion. No pending record is written —
 * the session entry tree and its
 * ``leaf`` pointer (identified by :attr:`leaf_id`) are already durably
 * persisted, so a later turn resumes straight from that tip.
 *
 * Attributes:
 * reason: The guard's suspend token — a human-readable rationale.
 * leaf_id: The session's active tip at suspend time (a persisted entry
 * id), the durable resume anchor.
 */
export type LoopSuspendedEvent = {
    timestamp?: string;
    kind?: string;
    reason?: string;
    leaf_id?: string;
};

