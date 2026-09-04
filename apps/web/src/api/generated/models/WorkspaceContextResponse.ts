/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ArtifactRefResponse } from './ArtifactRefResponse';
import type { ContextFocusResponse } from './ContextFocusResponse';
import type { ExperimentRefResponse } from './ExperimentRefResponse';
import type { HealthFlagResponse } from './HealthFlagResponse';
import type { KnowledgeRefResponse } from './KnowledgeRefResponse';
import type { ProjectRefResponse } from './ProjectRefResponse';
import type { RunRefResponse } from './RunRefResponse';
import type { WorkflowRefResponse } from './WorkflowRefResponse';
import type { WorkspaceRefResponse } from './WorkspaceRefResponse';
/**
 * Camel-cased HTTP view of the canonical ``WorkspaceContext`` read-model.
 */
export type WorkspaceContextResponse = {
    workspace: WorkspaceRefResponse;
    focus: ContextFocusResponse;
    projects?: Array<ProjectRefResponse>;
    experiments?: Array<ExperimentRefResponse>;
    workflows?: Array<WorkflowRefResponse>;
    recentRuns?: Array<RunRefResponse>;
    failedRuns?: Array<RunRefResponse>;
    runningRuns?: Array<RunRefResponse>;
    artifacts?: Array<ArtifactRefResponse>;
    knowledge?: Array<KnowledgeRefResponse>;
    openQuestions?: Array<KnowledgeRefResponse>;
    staleOrMissing?: Array<HealthFlagResponse>;
};

