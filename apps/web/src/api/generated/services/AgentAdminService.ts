/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { _CommandParseRequest } from '../models/_CommandParseRequest';
import type { AgentHealthResponse } from '../models/AgentHealthResponse';
import type { AgentToolListResponse } from '../models/AgentToolListResponse';
import type { CommandListResponse } from '../models/CommandListResponse';
import type { CommandParseResponse } from '../models/CommandParseResponse';
import type { KnowledgeSourcesResponse } from '../models/KnowledgeSourcesResponse';
import type { KnowledgeSourcesUpdateRequest } from '../models/KnowledgeSourcesUpdateRequest';
import type { McpSecretListResponse } from '../models/McpSecretListResponse';
import type { McpSecretPutRequest } from '../models/McpSecretPutRequest';
import type { McpServerListResponse } from '../models/McpServerListResponse';
import type { McpServerResponse } from '../models/McpServerResponse';
import type { McpServerTestResponse } from '../models/McpServerTestResponse';
import type { McpServerUpsertRequest } from '../models/McpServerUpsertRequest';
import type { ProviderResponse } from '../models/ProviderResponse';
import type { ProviderTestResponse } from '../models/ProviderTestResponse';
import type { ProviderUpdateRequest } from '../models/ProviderUpdateRequest';
import type { SkillListResponse } from '../models/SkillListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AgentAdminService {
    /**
     * Agent Health
     * Agent readiness for the UI banner — always 200, never the 503 catch-all.
     *
     * ``ready=False`` is a normal configuration state (no model / no API key).
     * The legacy ``agent.router`` catch-all used to 503 unknown ``/api/agent*``
     * paths, which made the UI treat "missing route" as "stack unavailable"
     * and permanently stop probing. This endpoint exists so health is always a
     * real JSON readiness document.
     * @param molabSession
     * @returns AgentHealthResponse Successful Response
     * @throws ApiError
     */
    public static agentHealth(
        molabSession?: (string | null),
    ): CancelablePromise<AgentHealthResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/health',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Commands
     * Slash-command catalog for the chat composer palette.
     *
     * Builtins always ship; skill-backed commands join when skill persistence
     * is wired (currently an empty skill catalog is valid).
     * @param molabSession
     * @returns CommandListResponse Successful Response
     * @throws ApiError
     */
    public static listCommands(
        molabSession?: (string | null),
    ): CancelablePromise<CommandListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/commands',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Parse Command
     * Parse a raw slash line into a builtin / skill / error result.
     * @param requestBody
     * @param molabSession
     * @returns CommandParseResponse Successful Response
     * @throws ApiError
     */
    public static parseCommand(
        requestBody: _CommandParseRequest,
        molabSession?: (string | null),
    ): CancelablePromise<CommandParseResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/agent/commands/parse',
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
     * List Skills
     * Return the configured skill catalog.
     *
     * Skill persistence is not wired into this admin service yet.  An empty
     * catalog is a valid state, so the read surface must not fall through to
     * the legacy agent 503 catch-all.
     * @param molabSession
     * @returns SkillListResponse Successful Response
     * @throws ApiError
     */
    public static listSkills(
        molabSession?: (string | null),
    ): CancelablePromise<SkillListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/skills',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Tools
     * Return agent tools: molab **builtins** + MCP groups when discovered.
     *
     * Builtins (``workspace_ensure``, ``run_land``, ``code_write``, …) are
     * always present with ``source="builtin"``. MCP tools attach as
     * ``source="mcp:<server>"`` when runtime discovery is connected; until
     * then ``mcpGroups`` may be empty without hiding builtins.
     * @param molabSession
     * @returns AgentToolListResponse Successful Response
     * @throws ApiError
     */
    public static listTools(
        molabSession?: (string | null),
    ): CancelablePromise<AgentToolListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/tools',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Provider
     * Current provider settings from the operator config (keys masked).
     * @param molabSession
     * @returns ProviderResponse Successful Response
     * @throws ApiError
     */
    public static getProvider(
        molabSession?: (string | null),
    ): CancelablePromise<ProviderResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/provider',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Provider
     * Persist submitted provider fields, then re-bridge the live process.
     *
     * The write goes through the shared :func:`set_operator_values` (same file,
     * same atomic writer as ``molab config set``). The bridged
     * ``molab.config`` keys this PUT changes are cleared before re-bridging so
     * the running server serves the new values immediately.
     * @param requestBody
     * @param molabSession
     * @returns ProviderResponse Successful Response
     * @throws ApiError
     */
    public static updateProvider(
        requestBody: ProviderUpdateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ProviderResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/agent/provider',
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
     * Test Provider
     * Preflight the agent stack for the submitted (or stored) model.
     *
     * Constructor + credential validation only — no disk writes, no network,
     * no LLM call (the honest scope of a settings-page "test" that must never
     * spend tokens or mutate state). ``reply`` describes what was verified.
     * @param requestBody
     * @param molabSession
     * @returns ProviderTestResponse Successful Response
     * @throws ApiError
     */
    public static testProvider(
        requestBody: ProviderUpdateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<ProviderTestResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/agent/provider/test',
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
     * List Mcp Servers
     * Merged user + workspace MCP server entries (workspace shadows user).
     * @param molabSession
     * @returns McpServerListResponse Successful Response
     * @throws ApiError
     */
    public static listMcpServers(
        molabSession?: (string | null),
    ): CancelablePromise<McpServerListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/mcp/servers',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Mcp Server
     * Upsert one MCP server entry at the requested scope.
     * @param requestBody
     * @param molabSession
     * @returns McpServerResponse Successful Response
     * @throws ApiError
     */
    public static createMcpServer(
        requestBody: McpServerUpsertRequest,
        molabSession?: (string | null),
    ): CancelablePromise<McpServerResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/agent/mcp/servers',
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
     * Replace Mcp Server
     * Replace one MCP server entry (name path must match body).
     * @param name
     * @param requestBody
     * @param molabSession
     * @returns McpServerResponse Successful Response
     * @throws ApiError
     */
    public static replaceMcpServer(
        name: string,
        requestBody: McpServerUpsertRequest,
        molabSession?: (string | null),
    ): CancelablePromise<McpServerResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/agent/mcp/servers/{name}',
            path: {
                'name': name,
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
     * Delete Mcp Server
     * Delete one MCP server entry at the given scope.
     * @param name
     * @param scope
     * @param molabSession
     * @returns void
     * @throws ApiError
     */
    public static deleteMcpServer(
        name: string,
        scope: string = 'user',
        molabSession?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/agent/mcp/servers/{name}',
            path: {
                'name': name,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'scope': scope,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Test Mcp Server
     * Best-effort stdio/HTTP reachability probe (list_tools when possible).
     * @param name
     * @param scope
     * @param molabSession
     * @returns McpServerTestResponse Successful Response
     * @throws ApiError
     */
    public static testMcpServer(
        name: string,
        scope: string = 'user',
        molabSession?: (string | null),
    ): CancelablePromise<McpServerTestResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/agent/mcp/servers/{name}/test',
            path: {
                'name': name,
            },
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'scope': scope,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Mcp Secrets
     * List secret *keys* (never values) at the given scope.
     * @param scope
     * @param molabSession
     * @returns McpSecretListResponse Successful Response
     * @throws ApiError
     */
    public static listMcpSecrets(
        scope: string = 'user',
        molabSession?: (string | null),
    ): CancelablePromise<McpSecretListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/mcp/secrets',
            cookies: {
                'molab_session': molabSession,
            },
            query: {
                'scope': scope,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Put Mcp Secret
     * Set or delete a secret value (empty value deletes).
     * @param key
     * @param requestBody
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static putMcpSecret(
        key: string,
        requestBody: McpSecretPutRequest,
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/agent/mcp/secrets/{key}',
            path: {
                'key': key,
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
     * Get Knowledge Sources
     * Read package pin from the molmcp MCP server entry (``MOLMCP_SOURCES``).
     * @param molabSession
     * @returns KnowledgeSourcesResponse Successful Response
     * @throws ApiError
     */
    public static getKnowledgeSources(
        molabSession?: (string | null),
    ): CancelablePromise<KnowledgeSourcesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/knowledge-sources',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Knowledge Sources
     * Write package pin onto the molmcp server's env (per-MCP, not global agent).
     * @param requestBody
     * @param molabSession
     * @returns KnowledgeSourcesResponse Successful Response
     * @throws ApiError
     */
    public static updateKnowledgeSources(
        requestBody: KnowledgeSourcesUpdateRequest,
        molabSession?: (string | null),
    ): CancelablePromise<KnowledgeSourcesResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/agent/knowledge-sources',
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
     * List Admin Providers
     * Provider form registry for Settings (bootstrap schema; never 503).
     * @param molabSession
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listAdminProviders(
        molabSession?: (string | null),
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/agent/admin/providers',
            cookies: {
                'molab_session': molabSession,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
