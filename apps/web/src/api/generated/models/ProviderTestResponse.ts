/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * POST /provider/test result — an honest preflight, not a chat reply.
 */
export type ProviderTestResponse = {
    ok: boolean;
    provider: string;
    model: string;
    latencyMs: number;
    reply: string;
    error?: (string | null);
};

