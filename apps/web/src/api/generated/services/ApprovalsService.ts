/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApprovalDecisionRequest } from '../models/ApprovalDecisionRequest';
import type { ApprovalDecisionResponse } from '../models/ApprovalDecisionResponse';
import type { PendingApprovalsResponse } from '../models/PendingApprovalsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ApprovalsService {
    /**
     * List Pending Approvals
     * List every pending approval across suspended plan + curate tasks.
     *
     * Empty ``items`` is normal — the inbox only fills when a plan/curate task
     * is suspended waiting for an operator decision. Not a 404.
     * @param molabSession
     * @returns PendingApprovalsResponse Successful Response
     * @throws ApiError
     */
    public static listPendingApprovals(
        molabSession?: (string | null),
    ): CancelablePromise<PendingApprovalsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/approvals',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Decide Approval
     * Record a ReviewDecision-shaped answer and resume/reject the task.
     *
     * Plan tasks delegate to :func:`molab.harness.services.plan_runtime.decide_plan_review`.
     * Curate tasks keep the binary store path (no ReviewPack yet).
     * @param taskKind
     * @param taskId
     * @param requestBody
     * @param molabSession
     * @returns ApprovalDecisionResponse Successful Response
     * @throws ApiError
     */
    public static decideApproval(
        taskKind: 'plan' | 'curate',
        taskId: string,
        requestBody: ApprovalDecisionRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ApprovalDecisionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/approvals/{task_kind}/{task_id}/decisions',
            path: {
                'task_kind': taskKind,
                'task_id': taskId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Stream Approval Events
     * SSE: one ``changed`` event per suspend/decision — the UI refetch signal.
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static streamApprovalEvents(
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/approvals/events',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
