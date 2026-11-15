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
     * `md` lands `<slug>.md`; `html` lands `<slug>.html` and `tex` lands `<slug>.tex` (body stored verbatim). Omitted, the class's own format: `tex` for a Manuscript, `md` for every other class. A format the class does not take is refused with 422.
     */
    format?: ('md' | 'html' | 'tex' | null);
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
        HYPOTHESIS = 'Hypothesis',
        DECISION = 'Decision',
        MANUSCRIPT = 'Manuscript',
    }
}

