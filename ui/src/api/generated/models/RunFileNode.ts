/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One node in a run's output file tree.
 *
 * On a folder, ``entryCount`` is how many children it really has and
 * ``truncated`` says ``children`` holds fewer — either because the
 * per-directory cap was hit or because the walk stopped at ``max_depth``.
 * A run that wrote 100k frames into one directory therefore costs a bounded
 * response instead of an unbounded one.
 */
export type RunFileNode = {
    assetId?: (string | null);
    assetKind?: (string | null);
    children?: Array<RunFileNode>;
    entryCount?: (number | null);
    modified?: (number | null);
    name: string;
    relPath: string;
    size?: (number | null);
    taskId?: (string | null);
    truncated?: boolean;
    type: string;
};

