/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CreateUserRequest = {
    username: string;
    password: string;
    role?: CreateUserRequest.role;
    workspaces?: Array<string>;
};
export namespace CreateUserRequest {
    export enum role {
        ADMIN = 'admin',
        OPERATOR = 'operator',
        VIEWER = 'viewer',
    }
}

