/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Invitation = {
    id: string;
    project_id: string;
    recipient_id: string;
    created_by: string;
    status: Invitation.status;
    created_at: string;
    expires_at: string;
    project_name?: (string | null);
    owner_name?: (string | null);
};
export namespace Invitation {
    export enum status {
        PENDING = 'pending',
        ACCEPTED = 'accepted',
        DECLINED = 'declined',
        REVOKED = 'revoked',
    }
}

