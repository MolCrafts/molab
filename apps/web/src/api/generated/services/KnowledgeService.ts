/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BacklinksResponse } from '../models/BacklinksResponse';
import type { Body_uploadDocMedia } from '../models/Body_uploadDocMedia';
import type { DocBodyUpdate } from '../models/DocBodyUpdate';
import type { DocCreateRequest } from '../models/DocCreateRequest';
import type { DocFieldsResponse } from '../models/DocFieldsResponse';
import type { DocFieldsUpdate } from '../models/DocFieldsUpdate';
import type { DocMediaResponse } from '../models/DocMediaResponse';
import type { DocMetaUpdate } from '../models/DocMetaUpdate';
import type { DocMoveRequest } from '../models/DocMoveRequest';
import type { DocPageResponse } from '../models/DocPageResponse';
import type { DocRelationsResponse } from '../models/DocRelationsResponse';
import type { DocRelationUpdate } from '../models/DocRelationUpdate';
import type { EmbedRequest } from '../models/EmbedRequest';
import type { EmbedResponse } from '../models/EmbedResponse';
import type { EntityBacklinksResponse } from '../models/EntityBacklinksResponse';
import type { KnowledgeGraphResponse } from '../models/KnowledgeGraphResponse';
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
     * Knowledge documents citing one entity.
     *
     * Pure derived read (no reverse index persisted): resolves the entity,
     * then walks documents whose edges point at its reference. A run or an
     * experiment needs ``projectId`` + ``experimentId`` (and ``runId``); an
     * asset needs ``assetId`` alone, since its id is unique in the workspace.
     * 404 on an unresolvable entity — never an empty-list fallback
     * for a bad ref.
     * @param kind Entity kind.
     * @param projectId
     * @param experimentId
     * @param runId
     * @param assetId
     * @param molabSession
     * @returns EntityBacklinksResponse Successful Response
     * @throws ApiError
     */
    public static entityBacklinks(
        kind: 'run' | 'experiment' | 'asset',
        projectId?: (string | null),
        experimentId?: (string | null),
        runId?: (string | null),
        assetId?: (string | null),
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
                'assetId': assetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Knowledge
     * Search registered wikis and this workspace — the CLI's ``knowledge search``.
     *
     * The workspace corpus goes through ``Knowledge.search`` on the workspace
     * disk. Registered sources are fused by :meth:`KnowledgeSourceStore.search`,
     * which is the same function the CLI calls.
     * @param q Case-insensitive needle (path/title/tags/body).
     * @param cls Only documents of this class or a subclass.
     * @param tag Only documents carrying this tag.
     * @param molabSession
     * @returns KnowledgeSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchKnowledge(
        q: string,
        cls?: ('Note' | 'Literature' | 'Report' | 'Finding' | 'Plan' | 'Roadmap' | 'Todo' | 'Milestone' | 'Observation' | 'Hypothesis' | 'Decision' | 'Manuscript' | null),
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
                'cls': cls,
                'tag': tag,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Knowledge
     * List every Knowledge document.
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
     * Get Knowledge Graph
     * The whole knowledge graph: the unfiltered listing as nodes, typed links as edges.
     *
     * Pure derived read. Nothing is indexed.
     * @param molabSession
     * @returns KnowledgeGraphResponse Successful Response
     * @throws ApiError
     */
    public static getKnowledgeGraph(
        molabSession?: (string | null),
    ): CancelablePromise<KnowledgeGraphResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/graph',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Note
     * Return one document's full body.
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
     * Create one knowledge class under *hostPath* (the workspace root when omitted).
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
     * Rewrite a document's narrative — ``Knowledge.write`` for every knowledge class.
     * @param path The note Concept's workspace-relative document path (its identity).
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
     * Rename and/or move a document onto another host.
     * @param path The note Concept's workspace-relative document path (its identity).
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
     * Delete a document. Inbound links are left dangling.
     * @param path The note Concept's workspace-relative document path (its identity).
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
     * Embed a live entity into a document — one typed edge via ``append_link``.
     *
     * Resolves the source document (404 on miss) and the target entity
     * (``run`` / ``experiment`` / ``asset`` / ``reference``; 404 on miss), then
     * writes ONE typed provenance edge to it.
     * @param path The source note Concept's workspace-relative document path.
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
     * Set a document's tags — ``Knowledge.write`` for every knowledge class.
     * @param path The note Concept's workspace-relative document path (its identity).
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
     * Get Doc Relations
     * Editable typed narrative links and the digest they were read from.
     * @param path
     * @param molabSession
     * @returns DocRelationsResponse Successful Response
     * @throws ApiError
     */
    public static getDocRelations(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<DocRelationsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/doc/relations',
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
     * Update Doc Relation
     * Edit the original markdown link; reject stale authoring with 409.
     * @param path
     * @param requestBody
     * @param molabSession
     * @returns DocRelationsResponse Successful Response
     * @throws ApiError
     */
    public static updateDocRelation(
        path: string,
        requestBody: DocRelationUpdate,
        molabSession?: (string | null),
    ): CancelablePromise<DocRelationsResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/knowledge/doc/relations',
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
     * Get Doc Fields
     * A document's own fields and its file digest (for ``ifMatch``).
     * @param path The document's workspace-relative path (its identity).
     * @param molabSession
     * @returns DocFieldsResponse Successful Response
     * @throws ApiError
     */
    public static getDocFields(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<DocFieldsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/doc/fields',
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
     * Replace Doc Fields
     * Replace a document's own fields whole — 409 when ``ifMatch`` is stale.
     *
     * The class's fields check them: a key it does not declare, or a value it
     * refuses, answers 422. The change is recorded in the workspace history as
     * ``knowledge.fields_replaced``.
     * @param path The document's workspace-relative path (its identity).
     * @param requestBody
     * @param molabSession
     * @returns DocFieldsResponse Successful Response
     * @throws ApiError
     */
    public static replaceDocFields(
        path: string,
        requestBody: DocFieldsUpdate,
        molabSession?: (string | null),
    ): CancelablePromise<DocFieldsResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/knowledge/doc/fields',
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
     * Return every document linking at *path*.
     * @param path The target Concept's workspace-relative document path (its identity).
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
     * Export a document: a markdown narrative, or the HTML or TeX document whole.
     * @param path The note Concept's workspace-relative document path (its identity).
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
    /**
     * Get Doc Bibliography
     * A Manuscript's bibliography: one BibTeX entry per Literature it cites.
     *
     * The same verb as ``molab knowledge bib`` (``Manuscript.bibliography``).
     * 422 when the document is not a Manuscript or a ``\cite`` key names no
     * Literature document.
     * @param path The Manuscript's workspace-relative document path.
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getDocBibliography(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/doc/bib',
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
     * Doc Page
     * Render a document the way a reader sees it, as one self-contained page.
     *
     * The same page ``molab knowledge serve --export`` writes: markdown rendered,
     * sources listed, assets inlined. 404 when the document or an asset it shows
     * is missing.
     * @param path The document's workspace-relative path (its identity).
     * @param molabSession
     * @returns DocPageResponse Successful Response
     * @throws ApiError
     */
    public static docPage(
        path: string,
        molabSession?: (string | null),
    ): CancelablePromise<DocPageResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/doc/page',
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
     * Upload Doc Media
     * Write one image beside the document, under ``knowledges/figs/``.
     * @param path The document the figure belongs to.
     * @param formData
     * @param molabSession
     * @returns DocMediaResponse Successful Response
     * @throws ApiError
     */
    public static uploadDocMedia(
        path: string,
        formData: Body_uploadDocMedia,
        molabSession?: (string | null),
    ): CancelablePromise<DocMediaResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/knowledge/doc/media',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'path': path,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Notebook
     * Zip one host's documents, the figures they cite, and an embed list.
     * @param hostPath Workspace-relative host. Empty exports the workspace root's documents.
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static exportNotebook(
        hostPath: string = '',
        molabSession?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/knowledge/export',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'hostPath': hostPath,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
