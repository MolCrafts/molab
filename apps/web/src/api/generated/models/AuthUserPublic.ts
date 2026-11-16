/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Wire-safe user summary (no password hash).
 */
export type AuthUserPublic = {
    username: string;
    role: AuthUserPublic.role;
    workspaces?: Array<string>;
    disabled?: boolean;
    created_at?: string;
    updated_at?: string;
};
export namespace AuthUserPublic {
    export enum role {
        ADMIN = 'admin',
        OPERATOR = 'operator',
        VIEWER = 'viewer',
    }
}

