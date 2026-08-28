/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Result of an interactive / OTP SSH login.
 */
export type WorkspaceConnectResponse = {
    host: string;
    key: string;
    /**
     * True when OpenSSH ControlMaster is accepting clients after login
     */
    masterAlive: boolean;
    message?: string;
    ok: boolean;
};

