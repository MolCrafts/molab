/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Body for ``POST /api/workspaces/{key}/connect``.
 */
export type WorkspaceConnectRequest = {
    /**
     * One-time verification code / OTP from the authenticator app or SMS
     */
    code: string;
    /**
     * Re-authenticate even when a ControlMaster is already alive
     */
    force?: boolean;
};

