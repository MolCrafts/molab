/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Form fields for one path. There is one rule per path.
 */
export type SyncRuleWrite = {
    path: string;
    kind: string;
    direction?: string;
    content?: string;
    types?: Array<string>;
    extraFiles?: string;
    when?: string;
    intervalMinutes?: number;
};

