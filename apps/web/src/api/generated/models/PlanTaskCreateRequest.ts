/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Body for starting a PlanOrchestrator background task.
 */
export type PlanTaskCreateRequest = {
    /**
     * Natural-language experiment draft for PlanOrchestrator.
     */
    draft: string;
    /**
     * Model id; defaults to the configured agent.model.
     */
    model?: (string | null);
    /**
     * Ground task binding against the molcrafts toolchain via the configured molmcp MCP server. Skips with a notice when molmcp is unavailable.
     */
    ground?: boolean;
    /**
     * Append the real-execution tail (ExecuteWorkflow -> GenerateFinalReport -> ApprovalGate(approve_execution) -> GenerateAuditReport). Runs the materialized driver as an executor subprocess OF THE SERVER HOST — exactly what the CLI does on its host; it never schedules to molq. Every gate suspends into the approvals inbox.
     */
    execute?: boolean;
    /**
     * Named workspace compute target for the step-9 DESCRIPTIVE execution report. Unknown names are rejected (422) listing the known targets.
     */
    compute_target?: (string | null);
    /**
     * Optional molmcp package allowlist (e.g. molpy, molvis, molplot). When null, uses agent.knowledge_sources from operator config; empty list means unrestricted.
     */
    knowledgeSources?: (Array<string> | null);
};

