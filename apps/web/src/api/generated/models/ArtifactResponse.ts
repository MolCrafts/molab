/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ArtifactResponse = {
    id: string;
    executionId: string;
    runId: string;
    projectId: string;
    name: string;
    sourcePath: string;
    digest: string;
    size: number;
    contentKind: string;
    mediaType?: (string | null);
    semanticType?: (string | null);
    declarationId?: (string | null);
    inputEntityIds?: Array<string>;
    metadata?: Record<string, any>;
    createdAt: string;
};

