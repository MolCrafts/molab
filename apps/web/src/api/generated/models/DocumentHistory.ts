/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FileRevision } from './FileRevision';
/**
 * Git versions of one served knowledge file and an optional working-copy comparison.
 */
export type DocumentHistory = {
    available: boolean;
    revisions: Array<FileRevision>;
    commit?: (string | null);
    body?: (string | null);
    diff?: (string | null);
};
