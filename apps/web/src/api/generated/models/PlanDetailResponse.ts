/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PlanFile } from './PlanFile';
import type { PlanTaskInfo } from './PlanTaskInfo';
/**
 * Full plan deliverables for the plan bundle (and legacy nine-step artifacts).
 *
 * Primary kinds: ``experimentPlan`` (spec + task board), ``planReport``,
 * ``frozenExperimentPlan``, ``boundWorkflow``, then codegen/compile outputs.
 * Legacy nine-step fields remain so older runs still render.
 */
export type PlanDetailResponse = {
    runId: string;
    executionId: string;
    projectId: string;
    experimentId: string;
    title: string;
    status: string;
    draft: string;
    experimentReport: (Record<string, any> | null);
    experimentPlan?: (Record<string, any> | null);
    frozenExperimentPlan?: (Record<string, any> | null);
    planReport?: (Record<string, any> | null);
    boundWorkflow?: (Record<string, any> | null);
    interventionRequest?: (Record<string, any> | null);
    experimentSpec: (Record<string, any> | null);
    experimentSpecYaml: (string | null);
    capabilities: (string | null);
    capabilitySelection: (Record<string, any> | null);
    workflowIr: (Record<string, any> | null);
    workflowIrYaml: (string | null);
    tasks: Array<PlanTaskInfo>;
    workflowSource: (string | null);
    workflowFiles: Array<PlanFile>;
    testFiles: Array<PlanFile>;
    inputSet: (Record<string, any> | null);
    dryRun: (Record<string, any> | null);
    planReview: (Record<string, any> | null);
    executionReport: (Record<string, any> | null);
    execution: (Record<string, any> | null);
    finalReport: (Record<string, any> | null);
    auditReport: (Record<string, any> | null);
    artifactKinds: Array<string>;
    hasWorkflow: boolean;
};

