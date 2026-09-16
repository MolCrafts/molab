/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Per-execution stdout/stderr for a run, as a bounded tail window.
 *
 * ``execution_id`` is the attempt these logs belong to; the server
 * defaults to the most recent attempt when no specific execution is
 * requested.  Each value is a window over
 * ``executions/<execution_id>/{stdout,stderr}.log`` (or ``None`` if the
 * file is absent — e.g. local executions skip stdout capture).
 *
 * A run's stdout can be gigabytes, so the server returns at most
 * ``max_bytes`` of it — by default the *tail*, which is what a log viewer
 * wants.  The cursor triple makes incremental follow possible: pass
 * ``stdout_end`` back as ``since_stdout`` and the next poll returns only
 * what was appended.  ``*_truncated`` says the window is not the whole
 * file, so a viewer can offer "load earlier".
 */
export type RunLogsResponse = {
    execution_id?: (string | null);
    stderr?: (string | null);
    stderr_end?: (number | null);
    stderr_offset?: (number | null);
    stderr_total?: (number | null);
    stderr_truncated?: boolean;
    stdout?: (string | null);
    stdout_end?: (number | null);
    stdout_offset?: (number | null);
    stdout_total?: (number | null);
    stdout_truncated?: boolean;
};

