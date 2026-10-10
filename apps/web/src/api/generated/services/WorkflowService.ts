/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkflowDocumentRequest } from '../models/WorkflowDocumentRequest';
import type { WorkflowDocumentResponse } from '../models/WorkflowDocumentResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class WorkflowService {
    /**
     * Put Workflow Document
     * Bind a normalized workflow IR as the document kind.
     *
     * Legacy experiments are 409 (migrate first). Code-kind experiments are
     * 409 unless ``convertToDocument`` is set. Invalid IR, including an
     * unregistered ``task_type``, is 400. Nothing is written on 409 or 400.
     * @param projectId
     * @param experimentId
     * @param requestBody
     * @param molabSession
     * @returns WorkflowDocumentResponse Successful Response
     * @throws ApiError
     */
    public static putWorkflowDocument(
        projectId: string,
        experimentId: string,
        requestBody: WorkflowDocumentRequest,
        molabSession?: (string | null),
    ): CancelablePromise<WorkflowDocumentResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/workflow',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
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
     * Get Workflow Document
     * Return the persisted workflow IR document, or 404 if none stored.
     * @param projectId
     * @param experimentId
     * @param molabSession
     * @returns WorkflowDocumentResponse Successful Response
     * @throws ApiError
     */
    public static getWorkflowDocument(
        projectId: string,
        experimentId: string,
        molabSession?: (string | null),
    ): CancelablePromise<WorkflowDocumentResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/projects/{project_id}/experiments/{experiment_id}/workflow',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Put Workflow Document
     * Bind a normalized workflow IR as the document kind.
     *
     * Legacy experiments are 409 (migrate first). Code-kind experiments are
     * 409 unless ``convertToDocument`` is set. Invalid IR, including an
     * unregistered ``task_type``, is 400. Nothing is written on 409 or 400.
     * @param projectId
     * @param experimentId
     * @param ws
     * @param requestBody
     * @param molabSession
     * @returns WorkflowDocumentResponse Successful Response
     * @throws ApiError
     */
    public static putWorkflowDocumentWs(
        projectId: string,
        experimentId: string,
        ws: string,
        requestBody: WorkflowDocumentRequest,
        molabSession?: (string | null),
    ): CancelablePromise<WorkflowDocumentResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/workflow',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
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
     * Get Workflow Document
     * Return the persisted workflow IR document, or 404 if none stored.
     * @param projectId
     * @param experimentId
     * @param ws
     * @param molabSession
     * @returns WorkflowDocumentResponse Successful Response
     * @throws ApiError
     */
    public static getWorkflowDocumentWs(
        projectId: string,
        experimentId: string,
        ws: string,
        molabSession?: (string | null),
    ): CancelablePromise<WorkflowDocumentResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/workspaces/{ws}/projects/{project_id}/experiments/{experiment_id}/workflow',
            path: {
                'project_id': projectId,
                'experiment_id': experimentId,
                'ws': ws,
            },
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
