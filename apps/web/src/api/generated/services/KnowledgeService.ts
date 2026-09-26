/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BacklinksResponse } from '../models/BacklinksResponse';
import type { DocBodyUpdate } from '../models/DocBodyUpdate';
import type { DocCreateRequest } from '../models/DocCreateRequest';
import type { DocMetaUpdate } from '../models/DocMetaUpdate';
import type { DocMoveRequest } from '../models/DocMoveRequest';
import type { EmbedRequest } from '../models/EmbedRequest';
import type { EmbedResponse } from '../models/EmbedResponse';
import type { EntityBacklinksResponse } from '../models/EntityBacklinksResponse';
import type { KnowledgeListResponse } from '../models/KnowledgeListResponse';
import type { KnowledgeSearchResponse } from '../models/KnowledgeSearchResponse';
import type { MessageResponse } from '../models/MessageResponse';
import type { NoteDetailResponse } from '../models/NoteDetailResponse';
import type { NoteSummary } from '../models/NoteSummary';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class KnowledgeService {
    /**
     * Entity Backlinks
     * Knowledge documents citing one entity — a thin ``Bundle.backlinks`` read.
     *
     * Pure derived read (no reverse index persisted): resolves the entity
     * Folder, then asks the bundle which Concepts' ``index.md`` edges point at
     * it. 404 on an unresolvable entity — never an empty-list fallback for a
     * bad ref (no-fallback law).
     * @param kind Entity kind.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param molabSession
     * @returns EntityBacklinksResponse Successful Response
     * @throws ApiError
     */
    public static entityBacklinks(
        kind: 'run' | 'experiment',
        projectId: string,
        experimentId: string,
        runId?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<EntityBacklinksResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/entity-backlinks',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'kind': kind,
                'projectId': projectId,
                'experimentId': experimentId,
                'runId': runId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Knowledge
     * Search the workspace knowledge tree — wraps ``Knowledge.search``.
     * @param q Case-insensitive needle (path/title/tags/body).
     * @param type Exact Knowledge class name.
     * @param tag Only documents carrying this tag.
     * @param molabSession
     * @returns KnowledgeSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchKnowledge(
        q: string,
        type?: (string | null),
        tag?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<KnowledgeSearchResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/search',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'q': q,
                'type': type,
                'tag': tag,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Knowledge
     * List every Knowledge document under the workspace via ``Knowledge.walk``.
     * @param tag Only notes carrying this tag.
     * @param status Only notes with this lifecycle status.
     * @param molabSession
     * @returns KnowledgeListResponse Successful Response
     * @throws ApiError
     */
    public static listKnowledge(
        tag?: (string | null),
        status?: (string | null),
        molabSession?: (string | null),
    ): CancelablePromise<KnowledgeListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'tag': tag,
                'status': status,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Note
     * Return one document's full body via ``Knowledge.open``.
     * @param path The document's workspace-relative path (its identity).
     * @param molabSession
     * @returns NoteDetailResponse Successful Response
     * @throws ApiError
     */
    public static getNote(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<NoteDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/note',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Doc
     * Create a :class:`Note` document — delegates to ``Bundle.create_note``.
     * @param requestBody
     * @param molabSession
     * @returns NoteSummary Successful Response
     * @throws ApiError
     */
    public static createDoc(
        requestBody: DocCreateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<NoteSummary> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/knowledge/doc',
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
     * Edit Doc
     * Rewrite a document's narrative — ``Knowledge.write`` for all six classes.
     * @param path The note Concept's bundle-relative path (its identity).
     * @param requestBody
     * @param molabSession
     * @returns NoteDetailResponse Successful Response
     * @throws ApiError
     */
    public static editDoc(
        path: string,
        requestBody: DocBodyUpdate,
        molabSession?: (string | null),
    ): CancelablePromise<NoteDetailResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/knowledge/doc',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Move Doc
     * Rename and/or reparent a note — delegates to ``Bundle.rename_note`` / ``move_note``.
     * @param path The note Concept's bundle-relative path (its identity).
     * @param requestBody
     * @param molabSession
     * @returns NoteSummary Successful Response
     * @throws ApiError
     */
    public static moveDoc(
        path: string,
        requestBody: DocMoveRequest,
        molabSession?: (string | null),
    ): CancelablePromise<NoteSummary> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/knowledge/doc',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Doc
     * Delete a note (its directory subtree) — delegates to ``Bundle.delete_note``.
     * @param path The note Concept's bundle-relative path (its identity).
     * @param molabSession
     * @returns MessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteDoc(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<MessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/knowledge/doc',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Embed Doc
     * Embed a live entity into a document — delegates to the knowledge edge writer.
     *
     * Resolves the source ``Note`` (404 on miss / non-note) and the target entity
     * (``run`` / ``experiment`` / ``asset`` / ``reference``; 404 on miss), then
     * writes ONE typed provenance edge via ``Bundle.link`` at the target resolved
     * by :func:`~molab.knowledge.embed.resolve_embed_target` — the same verb the CLI
     * uses, so the edge-writing logic is never re-built at the HTTP boundary.
     * @param path The source note Concept's bundle-relative path.
     * @param requestBody
     * @param molabSession
     * @returns EmbedResponse Successful Response
     * @throws ApiError
     */
    public static embedDoc(
        path: string,
        requestBody: EmbedRequest,
        molabSession?: (string | null),
    ): CancelablePromise<EmbedResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/knowledge/doc/embed',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Doc Meta
     * Update a document's tags/status — ``Knowledge.write`` for all six classes.
     * @param path The note Concept's bundle-relative path (its identity).
     * @param requestBody
     * @param molabSession
     * @returns NoteSummary Successful Response
     * @throws ApiError
     */
    public static updateDocMeta(
        path: string,
        requestBody: DocMetaUpdate,
        molabSession?: (string | null),
    ): CancelablePromise<NoteSummary> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/knowledge/doc/meta',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Backlinks
     * Return every Concept linking at *path* — delegates to ``Bundle.backlinks``.
     * @param path The target Concept's bundle-relative path (its identity).
     * @param molabSession
     * @returns BacklinksResponse Successful Response
     * @throws ApiError
     */
    public static getBacklinks(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<BacklinksResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/backlinks',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Doc
     * Export a note as portable Markdown — delegates to ``Bundle.export_markdown``.
     * @param path The note Concept's bundle-relative path (its identity).
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportDoc(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/doc/export',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
