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
 * The same document ``molab workflow dry-run --json`` prints for a script.
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
};

