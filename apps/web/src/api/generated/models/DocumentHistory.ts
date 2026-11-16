/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentVersion } from './DocumentVersion';
/**
 * A knowledge file's versions, newest first, and an optional comparison with its working copy.
 */
export type DocumentHistory = {
    available: boolean;
    versions: Array<DocumentVersion>;
    uncommitted?: boolean;
    version?: (number | null);
    diff?: (string | null);
};

