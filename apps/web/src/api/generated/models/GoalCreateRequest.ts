/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GoalCreateRequest = {
    /**
     * Natural language goal description
     */
    description: string;
    constraints?: Record<string, any>;
    successCriteria?: Array<string>;
    projectId?: (string | null);
    experimentId?: (string | null);
    runId?: (string | null);
    /**
     * Agent for the first turn. 'chat' = interactive loop; 'plan' = auditable Plan Mode pipeline. Canonical field — no plan_mode alias.
     */
    mode?: GoalCreateRequest.mode;
    /**
     * Replace the layered system prompt for this single session. Workspace and skill addenda are bypassed; the molab built-in preamble is also dropped.
     */
    instructionsOverride?: (string | null);
    /**
     * When the goal originates from a slash command, the underlying skill id (informational; the route still resolves the skill's instructions server-side).
     */
    skillId?: (string | null);
};
export namespace GoalCreateRequest {
    /**
     * Agent for the first turn. 'chat' = interactive loop; 'plan' = auditable Plan Mode pipeline. Canonical field — no plan_mode alias.
     */
    export enum mode {
        CHAT = 'chat',
        PLAN = 'plan',
    }
}

