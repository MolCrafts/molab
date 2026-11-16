/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Words a run's latest attempt can show, plus ``pending``.
 *
 * ``pending`` is the label when the run has no attempt yet. Every other
 * value is an :class:`~molab.workspace.domain.ExecutionStatus`. The
 * terminal and retryable sets live next to that enum; this list is not a
 * second, shorter vocabulary.
 *
 * Lives here (the workspace schema source of truth) rather than in
 * ``run.py`` so the run-lifecycle collaborators can import it without a
 * circular ``run.py`` dependency. Re-exported from ``run.py`` for
 * backward compatibility (``from molab.workspace.run import RunStatus``).
 */
export enum RunStatus {
    PENDING = 'pending',
    QUEUED = 'queued',
    RUNNING = 'running',
    FINALIZING = 'finalizing',
    SUCCEEDED = 'succeeded',
    FAILED = 'failed',
    CANCELLED = 'cancelled',
    INTERRUPTED = 'interrupted',
}
