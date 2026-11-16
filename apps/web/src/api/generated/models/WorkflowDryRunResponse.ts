/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkflowDryRunBranch } from './WorkflowDryRunBranch';
import type { WorkflowDryRunExperiment } from './WorkflowDryRunExperiment';
import type { WorkflowDryRunRun } from './WorkflowDryRunRun';
import type { WorkflowDryRunTask } from './WorkflowDryRunTask';
import type { WorkflowDryRunWorkflow } from './WorkflowDryRunWorkflow';
/**
 * The walk of an experiment's stored workflow, without running a task.
 *
 * ``source=code`` shares the CLI's source preview. ``source=stored`` is
 * the saved graph and registered inventory, not a current source sweep.
 */
export type WorkflowDryRunResponse = {
    experiment: WorkflowDryRunExperiment;
    workflow: WorkflowDryRunWorkflow;
    /**
     * Ready tasks per step, earliest first; a wave can run together
     */
    waves: Array<Array<string>>;
    branches?: Array<WorkflowDryRunBranch>;
    runs?: Array<WorkflowDryRunRun>;
    tasks?: Array<WorkflowDryRunTask>;
    source?: WorkflowDryRunResponse.source;
    definitionHash?: (string | null);
    workflowHash?: (string | null);
    entrypoint?: (string | null);
    registeredRuns?: Array<WorkflowDryRunRun>;
};
export namespace WorkflowDryRunResponse {
    export enum source {
        STORED = 'stored',
        CODE = 'code',
    }
}

