/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AuthStatusResponse } from '../models/AuthStatusResponse';
import type { AuthTokenResponse } from '../models/AuthTokenResponse';
import type { AuthUserListResponse } from '../models/AuthUserListResponse';
import type { AuthUserPublic } from '../models/AuthUserPublic';
import type { CreateUserRequest } from '../models/CreateUserRequest';
import type { LoginRequest } from '../models/LoginRequest';
import type { PasswordRequest } from '../models/PasswordRequest';
import type { PatchUserRequest } from '../models/PatchUserRequest';
import type { SwitchRequest } from '../models/SwitchRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AuthService {
    /**
     * Auth Status
     * @param molabSession
     * @returns AuthStatusResponse Successful Response
     * @throws ApiError
     */
    public static authStatus(
        molabSession?: (string | null),
    ): CancelablePromise<AuthStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/auth/status',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Auth Login
     * @param requestBody
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static authLogin(
        requestBody: LoginRequest,
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Auth Logout
     * @param molabSession
     * @returns void
     * @throws ApiError
     */
    public static authLogout(
        molabSession?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/logout',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Auth Me
     * @param molabSession
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static authMe(
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/auth/me',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Auth Token
     * @param molabSession
     * @returns AuthTokenResponse Successful Response
     * @throws ApiError
     */
    public static authToken(
        molabSession?: (string | null),
    ): CancelablePromise<AuthTokenResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/auth/token',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Auth Refresh
     * @param molabSession
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static authRefresh(
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/refresh',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Auth Switch
     * @param requestBody
     * @param molabSession
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static authSwitch(
        requestBody: SwitchRequest,
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/switch',
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
     * List Users
     * @param molabSession
     * @returns AuthUserListResponse Successful Response
     * @throws ApiError
     */
    public static listUsers(
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/auth/users',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create User
     * @param requestBody
     * @param molabSession
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static createUser(
        requestBody: CreateUserRequest,
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/users',
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
     * Patch User
     * @param username
     * @param requestBody
     * @param molabSession
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static patchUser(
        username: string,
        requestBody: PatchUserRequest,
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/auth/users/{username}',
            path: {
                'username': username,
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
     * Delete User
     * @param username
     * @param molabSession
     * @returns void
     * @throws ApiError
     */
    public static deleteUser(
        username: string,
        molabSession?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/auth/users/{username}',
            path: {
                'username': username,
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
     * Set User Password
     * @param username
     * @param requestBody
     * @param molabSession
     * @returns AuthUserPublic Successful Response
     * @throws ApiError
     */
    public static setUserPassword(
        username: string,
        requestBody: PasswordRequest,
        molabSession?: (string | null),
    ): CancelablePromise<AuthUserPublic> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/auth/users/{username}/password',
            path: {
                'username': username,
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
}
