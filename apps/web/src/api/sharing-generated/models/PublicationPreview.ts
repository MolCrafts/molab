/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublishedExperiment } from './PublishedExperiment';
import type { PublishedProject } from './PublishedProject';
import type { PublishedRun } from './PublishedRun';
export type PublicationPreview = {
    schema_version?: number;
    workspace_id: string;
    project: PublishedProject;
    experiments: Array<PublishedExperiment>;
    runs: Array<PublishedRun>;
};

