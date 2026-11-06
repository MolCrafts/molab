/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ExecutionEvidenceResponse } from './ExecutionEvidenceResponse';
import type { ManagedAssetResponse } from './ManagedAssetResponse';
import type { RunFileNode } from './RunFileNode';
export type ExecutionOutputsResponse = {
    executionId: string;
    stdout?: (string | null);
    stderr?: (string | null);
    runtime?: (string | null);
    assets?: Array<ManagedAssetResponse>;
    evidence?: Array<ExecutionEvidenceResponse>;
    unregistered?: Array<RunFileNode>;
    results?: Record<string, any>;
};

