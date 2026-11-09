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
    record?: (Record<string, any> | null);
    createdBy?: string;
    title?: (string | null);
    authors?: (Array<string> | null);
    year?: (number | null);
    doi?: (string | null);
    venue?: (string | null);
    url?: (string | null);
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
        ROADMAP = 'Roadmap',
        TODO = 'Todo',
        MILESTONE = 'Milestone',
        OBSERVATION = 'Observation',
        DELEGATION = 'Delegation',
    }
}

