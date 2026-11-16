/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublishedProject } from './PublishedProject';
export type BeginPublication = {
    schema_version?: number;
    workspace_id: string;
    project: PublishedProject;
    base_version?: (string | null);
    activate?: boolean;
};

