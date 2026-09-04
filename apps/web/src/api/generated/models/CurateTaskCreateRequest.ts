/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Body for starting a curation-flow background task.
 */
export type CurateTaskCreateRequest = {
    /**
     * Natural-language workspace-curation request.
     */
    request: string;
    /**
     * Model id; defaults to the configured agent.model.
     */
    model?: (string | null);
};

