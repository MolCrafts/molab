/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RunStatusSummaryResponse } from './RunStatusSummaryResponse';
/**
 * One immutable Run definition in the experiment comparison matrix.
 */
export type ComparisonRunRow = {
    runId: string;
    definitionHash: string;
    experimentRevisionId: string;
    inputAssetIds?: Array<string>;
    statusSummary: RunStatusSummaryResponse;
    parameters?: Record<string, any>;
    created: string;
};

