/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SyncRuleResponse = {
    id: string;
    path: string;
    kind: string;
    direction: string;
    content: string;
    types: Array<string>;
    extraFiles: string;
    when: string;
    intervalMinutes: number;
    lastRunAt?: (string | null);
    lastStatus?: (string | null);
    lastOutput?: (string | null);
};

