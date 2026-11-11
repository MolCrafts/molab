/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One of an attempt's directories, and what it promises.
 *
 * Sent so a client never has to know a layout. Which directory holds
 * results, and which is scratch it should not chart, is answered by these
 * flags — the same declaration the server itself queries.
 */
export type ExecutionDirResponse = {
    name: string;
    purpose: string;
    versioned: boolean;
    products: boolean;
};

