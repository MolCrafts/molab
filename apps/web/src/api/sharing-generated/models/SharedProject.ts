/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublishedProject } from './PublishedProject';
export type SharedProject = {
    id: string;
    project: (PublishedProject | null);
    owner_id: string;
    owner_name: string;
    role: SharedProject.role;
    active: boolean;
    version_id: (string | null);
    published_at: (string | null);
    source_seen_at: (string | null);
};
export namespace SharedProject {
    export enum role {
        OWNER = 'owner',
        VIEWER = 'viewer',
    }
}

