/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RunStatusSummaryResponse } from './RunStatusSummaryResponse';
export type RunSummary = {
    id: string;
    statusSummary: RunStatusSummaryResponse;
    created: string;
    finished?: (string | null);
    parameters?: Record<string, any>;
};

