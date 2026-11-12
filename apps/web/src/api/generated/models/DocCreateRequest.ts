/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocCite } from './DocCite';
export type DocCreateRequest = {
    name: string;
    body?: string;
    hostPath?: (string | null);
    /**
     * `md` lands `<slug>.md`; `html` lands `<slug>.html` (body stored verbatim).
     */
    format?: DocCreateRequest.format;
    cls?: DocCreateRequest.cls;
    /**
     * What the document rests on: entity refs, http(s) URLs or DOIs, and workspace-relative files. A sourced class given none names its host.
     */
    sources?: Array<string>;
    /**
     * The fields the class declares (a Hypothesis `verdict`, a Literature's bibliography, a Note `status`); any other key is refused with 422.
     */
    fields?: Record<string, any>;
    /**
     * Typed edges to write with the document. A target that names nothing here is refused with 422 and nothing lands.
     */
    cites?: Array<DocCite>;
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

