/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocSource } from './DocSource';
export type DocCreateRequest = {
    name: string;
    body?: string;
    hostPath?: (string | null);
    cls?: DocCreateRequest.cls;
    sources?: Array<DocSource>;
    title?: (string | null);
    authors?: (Array<string> | null);
    year?: (number | null);
    doi?: (string | null);
    venue?: (string | null);
    url?: (string | null);
};
export namespace DocCreateRequest {
    export enum cls {
        NOTE = 'Note',
        LITERATURE = 'Literature',
        REPORT = 'Report',
        FINDING = 'Finding',
        PLAN = 'Plan',
        OBSERVATION = 'Observation',
    }
}

