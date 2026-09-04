/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * The gated-execution outcome for a deterministic curation request.
 */
export type CurateResponse = {
    proposalId: string;
    status: string;
    reason?: (string | null);
    resultArtifactIds?: Array<string>;
};

