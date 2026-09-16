/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MetricSeriesResponse } from './MetricSeriesResponse';
/**
 * Run-local metrics query response.
 *
 * ``nextOffset`` is the cheap cursor: a follow-up poll passing it as
 * ``since_offset`` seeks straight to the new bytes, so each poll costs what
 * was appended rather than the whole file so far.  ``nextLine`` is the
 * legacy line cursor, kept for callers that have not migrated; it still
 * forces a re-read from the top.  ``truncated`` means the scan stopped at
 * ``max_scan_bytes`` (or ``limit``) with more data available.
 */
export type RunMetricsResponse = {
    nextLine?: number;
    nextOffset?: number;
    parseErrors?: number;
    records?: Array<Record<string, any>>;
    series?: Array<MetricSeriesResponse>;
    truncated?: boolean;
};

