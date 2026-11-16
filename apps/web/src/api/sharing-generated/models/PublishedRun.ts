/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RunStatus } from './RunStatus';
import type { ScalarPoint } from './ScalarPoint';
export type PublishedRun = {
    id: string;
    experiment_id: string;
    name: string;
    status: RunStatus;
    parameters?: Record<string, (string | boolean | number | null)>;
    metrics?: Record<string, Array<ScalarPoint>>;
};

