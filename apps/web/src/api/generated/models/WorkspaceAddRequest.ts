/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * VS Code ``Add Folder to Workspace`` — append a root to the served set.
 */
export type WorkspaceAddRequest = {
    /**
     * ``local`` path or ``remote`` (registered target or Host:/path)
     */
    kind?: WorkspaceAddRequest.kind;
    /**
     * Local absolute path (kind=local) or SCP Host:/abs (kind=remote)
     */
    path?: (string | null);
    /**
     * Registered workspace-target name (kind=remote alternative to path)
     */
    name?: (string | null);
    /**
     * When kind=local, create the directory if it does not exist
     */
    create_if_missing?: boolean;
    /**
     * Switch active workspace to the newly added root
     */
    activate?: boolean;
};
export namespace WorkspaceAddRequest {
    /**
     * ``local`` path or ``remote`` (registered target or Host:/path)
     */
    export enum kind {
        LOCAL = 'local',
        REMOTE = 'remote',
    }
}

