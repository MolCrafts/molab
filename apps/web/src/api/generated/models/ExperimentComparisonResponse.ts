/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComparisonRunRow } from './ComparisonRunRow';
/**
 * Comparison matrix of scientific Run definitions only.
 */
export type ExperimentComparisonResponse = {
    experimentId: string;
    projectId: string;
    paramKeys?: Array<string>;
    runs?: Array<ComparisonRunRow>;
};

