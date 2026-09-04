/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SessionEventResponse } from './SessionEventResponse';
import type { SessionStatsResponse } from './SessionStatsResponse';
/**
 * User-facing task wrapper around one current runtime session.
 *
 * ``taskId`` is the product identifier the UI should route on; ``sessionId``
 * is the lower-level runtime handle used to continue the active execution.
 */
export type AgentTaskResponse = {
    taskId: string;
    title: string;
    goal: string;
    status: string;
    createdAt: string;
    updatedAt?: (string | null);
    sessionId: string;
    events?: Array<SessionEventResponse>;
    stats?: SessionStatsResponse;
    planMode?: boolean;
    activeMode?: AgentTaskResponse.activeMode;
    activeTurnId?: (string | null);
    activePlanTaskId?: (string | null);
    skillId?: (string | null);
    projectId?: (string | null);
    experimentId?: (string | null);
    runId?: (string | null);
};
export namespace AgentTaskResponse {
    export enum activeMode {
        CHAT = 'chat',
        PLAN = 'plan',
    }
}

