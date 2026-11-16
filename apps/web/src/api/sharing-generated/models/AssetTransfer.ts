/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Worker-only locator, derived from provisioned cluster identity bindings.
 */
export type AssetTransfer = {
    id: string;
    project_id: string;
    asset_id: string;
    recipient_id: string;
    title: string;
    digest: string;
    size: number;
    state: AssetTransfer.state;
    created_at: string;
    updated_at: string;
    owner_uid: number;
    recipient_uid: number;
    cluster_id: string;
    storage_id: string;
};
export namespace AssetTransfer {
    export enum state {
        PREPARING = 'preparing',
        ACTIVE = 'active',
        REVOKING = 'revoking',
        REVOKED = 'revoked',
    }
}

