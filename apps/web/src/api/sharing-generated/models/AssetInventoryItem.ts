/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AssetInventoryItem = {
    id: string;
    title: string;
    digest: string;
    size: number;
    kind: AssetInventoryItem.kind;
};
export namespace AssetInventoryItem {
    export enum kind {
        FILE = 'file',
        DIRECTORY = 'directory',
    }
}

