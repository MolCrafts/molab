/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocSource } from './DocSource';
export type DocCreateRequest = {
    name: string;
    body?: string;
    hostPath?: (string | null);
    /**
     * `md` lands `<slug>.md`; `html` lands `<slug>.html` (body stored verbatim).
     */
    format?: DocCreateRequest.format;
    cls?: DocCreateRequest.cls;
    sources?: Array<DocSource>;
    /**
     * The fields the class declares (a Hypothesis `verdict`, a Literature's bibliography, a Note `status`); any other key is refused with 422.
     */
    fields?: Record<string, any>;
    createdBy?: string;
};
export namespace DocCreateRequest {
    /**
     * `md` lands `<slug>.md`; `html` lands `<slug>.html` (body stored verbatim).
     */
    export enum format {
        MD = 'md',
        HTML = 'html',
    }
    export enum cls {
        NOTE = 'Note',
        LITERATURE = 'Literature',
        REPORT = 'Report',
        FINDING = 'Finding',
        PLAN = 'Plan',
        OBSERVATION = 'Observation',
        HYPOTHESIS = 'Hypothesis',
    }
}

