/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Live remote-index progress for the MolVis-style status bar.
 */
export type CacheStatusResponse = {
    /**
     * False when the active workspace is local
     */
    cached: boolean;
    connected?: (boolean | null);
    indexed?: (boolean | null);
    ready?: (boolean | null);
    indexing?: (boolean | null);
    phase?: string;
    total?: number;
    done?: number;
    percent?: (number | null);
    message?: string;
};

