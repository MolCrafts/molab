/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MetricSeriesResponse } from './MetricSeriesResponse';
/**
 * Run-local metrics query response.
 *
 * ``nextOffset`` is the cursor: a follow-up poll passing it as
 * ``since_offset`` seeks straight to the new bytes, so each poll costs what
 * was appended rather than the whole file so far.  ``truncated`` means the
 * scan stopped at ``max_scan_bytes`` (or ``limit``) with more data available.
 */
export type RunMetricsResponse = {
    nextOffset?: number;
    parseErrors?: number;
    records?: Array<Record<string, any>>;
    series?: Array<MetricSeriesResponse>;
    truncated?: boolean;
};

