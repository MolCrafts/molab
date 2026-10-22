/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AssetVersionResponse = {
    id: string;
    assetId: string;
    sourceArtifactId?: (string | null);
    originKind: AssetVersionResponse.originKind;
    originRef?: (string | null);
    originUri?: (string | null);
    importAction?: (string | null);
    version: number;
    digest?: (string | null);
    size?: (number | null);
    contentKind?: (string | null);
    mediaType?: (string | null);
    semanticType?: (string | null);
    metadata?: Record<string, any>;
    createdAt: string;
};
export namespace AssetVersionResponse {
    export enum originKind {
        ARTIFACT = 'artifact',
        IMPORT = 'import',
    }
}

