/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One source a sourced document is derived from.
 */
export type DocSource = {
    kind: DocSource.kind;
    ref: string;
};
export namespace DocSource {
    export enum kind {
        RUN = 'run',
        EXPERIMENT = 'experiment',
        ASSET = 'asset',
        PROJECT = 'project',
        REFERENCE = 'reference',
    }
}

