/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Per-execution stdout/stderr for a run.
 *
 * ``execution_id`` is the attempt these logs belong to; the server
 * defaults to the most recent attempt when no specific execution is
 * requested.  Each value is the full content of
 * ``executions/<execution_id>/{stdout,stderr}.log`` (written by
 * ``molab.print`` and ``ctx.log``, D92), falling back to a legacy
 * scheduler file under ``jobs/`` when the attempt has none, or ``None``.
 * An empty ``stdout`` falls back to the attempt's ``run.log``.
 */
export type RunLogsResponse = {
    executionId?: (string | null);
    stdout?: (string | null);
    stderr?: (string | null);
};

