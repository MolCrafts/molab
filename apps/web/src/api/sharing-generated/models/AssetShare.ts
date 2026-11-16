/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AssetShare = {
    id: string;
    project_id: string;
    asset_id: string;
    recipient_id: string;
    title: string;
    digest: string;
    size: number;
    state: AssetShare.state;
    created_at: string;
    updated_at: string;
};
export namespace AssetShare {
    export enum state {
        PREPARING = 'preparing',
        ACTIVE = 'active',
        REVOKING = 'revoking',
        REVOKED = 'revoked',
    }
}

