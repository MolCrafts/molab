/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ReplayEvent } from './ReplayEvent';
/**
 * An oldest-first page anchored at a fixed upper timestamp.
 */
export type ReplayPage = {
    events: Array<ReplayEvent>;
    total: number;
    offset: number;
    nextOffset: (number | null);
    asOf: string;
    historyAvailable: boolean;
    warnings?: Array<string>;
};
