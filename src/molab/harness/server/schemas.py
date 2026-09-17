"""Wire models for the harness's own HTTP surface.

Every request/response shape here belongs to a route the harness contributes
through :data:`molab.harness.server.SERVER_PLUGIN` — agent sessions and tasks,
slash commands, skills, tools, MCP servers and secrets. They live with the
routes that produce them rather than in molab's schema package, so the plugin
owns its wire the same way it owns its handlers.

They serialize like every other molab response: :class:`ApiModel` is the
camelCase wrapper (:mod:`molab.server.schemas._wire`), which molab owns
because it is the convention of the ``/api`` surface, not of any one plugin.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Discriminator, Field

from molab.server.schemas._wire import ApiModel


class GoalCreateRequest(ApiModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str = Field(..., description="Natural language goal description")
    constraints: dict[str, Any] = Field(default_factory=dict)
    success_criteria: list[str] = Field(default_factory=list)
    # Mount scope (vision-loop-11): the entity this session is attached to.
    # A session mounted on a run/experiment receives that entity's state as
    # a system-prompt context block; unresolvable ids 404 (never downgraded).
    project_id: str | None = Field(None, alias="projectId")
    experiment_id: str | None = Field(None, alias="experimentId")
    run_id: str | None = Field(None, alias="runId")
    mode: Literal["chat", "plan"] = Field(
        "chat",
        description=(
            "Agent for the first turn. 'chat' = interactive loop; "
            "'plan' = auditable Plan Mode pipeline. Canonical field — no "
            "plan_mode alias."
        ),
    )
    instructions_override: str | None = Field(
        None,
        description=(
            "Replace the layered system prompt for this single session. "
            "Workspace and skill addenda are bypassed; the molab built-in "
            "preamble is also dropped."
        ),
    )
    skill_id: str | None = Field(
        None,
        description=(
            "When the goal originates from a slash command, the underlying "
            "skill id (informational; the route still resolves the skill's "
            "instructions server-side)."
        ),
    )


class UserMessageCreateRequest(ApiModel):
    """Mid-session chat message from the user to the agent."""

    content: str = Field(..., description="User's message")
    mode: Literal["chat", "plan"] = Field(
        "chat",
        description="Agent used for this turn; replies to a pending request keep its agent.",
    )
    request_id: str | None = Field(
        None,
        description=(
            "Pending UserMessageRequestEvent id this message replies to "
            "(omit for an unsolicited follow-up)."
        ),
    )


class McpStdioSpecRequest(ApiModel):
    """Local subprocess MCP server spec."""

    type: Literal["stdio"] = "stdio"
    command: str = Field(..., min_length=1, max_length=4096)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Values may contain ${SECRET:KEY} placeholders.",
    )


class McpOAuth2AuthRequest(ApiModel):
    """OAuth 2.0 (Authorization Code + PKCE) auth for an HTTP MCP server.

    The actual token exchange happens via the dedicated /oauth/* endpoints;
    this is just the *intent* persisted in the spec. Empty ``scopes`` means
    "let the IdP pick". ``clientId`` is optional and only set when the
    target IdP doesn't support Dynamic Client Registration.
    """

    type: Literal["oauth2"]
    scopes: list[str] = Field(default_factory=list)
    clientId: str | None = Field(
        default=None,
        max_length=512,
        description="Pre-registered client_id; leave null to use Dynamic Client Registration.",
    )


class McpHttpSpecRequest(ApiModel):
    """Remote HTTP MCP server spec.

    Two transports: ``http`` (streamable HTTP, Claude Code convention)
    and ``sse`` (legacy long-poll). Use ``http`` for any new server.
    """

    type: Literal["http", "sse"]
    url: str = Field(..., min_length=1, max_length=4096)
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Values may contain ${SECRET:KEY} placeholders.",
    )
    auth: McpOAuth2AuthRequest | None = Field(
        default=None,
        description=(
            "Optional structured auth. When set, the runtime drives the "
            "OAuth flow and ignores any 'Authorization' header here."
        ),
    )


McpSpecRequest = Annotated[
    McpStdioSpecRequest | McpHttpSpecRequest,
    Discriminator("type"),
]


class McpServerUpsertRequest(ApiModel):
    """Create or replace an MCP server entry at the chosen scope."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "Server name; lowercase letters, digits, underscore, hyphen; "
            "must start with a letter or digit."
        ),
    )
    scope: Literal["user", "workspace"] = Field(
        "workspace",
        description="VSCode-style scope. Workspace overrides User on name collision.",
    )
    spec: McpSpecRequest = Field(..., discriminator="type")


class SessionEventResponse(ApiModel):
    type: str
    ts: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionStatsResponse(ApiModel):
    inputTokens: int = 0
    outputTokens: int = 0
    cacheReadTokens: int = 0
    cacheWriteTokens: int = 0
    totalTokens: int = 0
    requests: int = 0
    toolCalls: int = 0
    events: int = 0
    startedAt: str | None = None
    completedAt: str | None = None
    durationSeconds: float | None = None


class AgentSessionResponse(ApiModel):
    sessionId: str
    status: str
    goalDescription: str
    createdAt: str
    events: list[SessionEventResponse] = Field(default_factory=list)
    stats: SessionStatsResponse = Field(default_factory=SessionStatsResponse)
    planMode: bool = False
    skillId: str | None = None


class AgentSessionListResponse(ApiModel):
    sessions: list[AgentSessionResponse]
    total: int


class AgentTaskResponse(ApiModel):
    """User-facing task wrapper around one current runtime session.

    ``taskId`` is the product identifier the UI should route on; ``sessionId``
    is the lower-level runtime handle used to continue the active execution.
    """

    taskId: str
    title: str
    goal: str
    status: str
    createdAt: str
    updatedAt: str | None = None
    sessionId: str
    events: list[SessionEventResponse] = Field(default_factory=list)
    stats: SessionStatsResponse = Field(default_factory=SessionStatsResponse)
    planMode: bool = False
    activeMode: Literal["chat", "plan"] = "chat"
    activeTurnId: str | None = None
    activePlanTaskId: str | None = None
    skillId: str | None = None
    #: Plan / mount scope — the same ids used by plan_emitted and Deliverables.
    projectId: str | None = None
    experimentId: str | None = None
    runId: str | None = None


class AgentTaskListResponse(ApiModel):
    tasks: list[AgentTaskResponse]
    total: int


class CommandParameterSpec(ApiModel):
    """One ``{{param}}`` slot in a slash command's goal_template."""

    name: str
    required: bool = True


class CommandSpec(ApiModel):
    """A single slash command — skill-backed or builtin."""

    slashName: str
    name: str
    description: str = ""
    parameters: list[CommandParameterSpec] = Field(default_factory=list)
    defaultPlanMode: bool = False
    isBuiltin: bool = False
    skillId: str | None = None


class CommandListResponse(ApiModel):
    commands: list[CommandSpec] = Field(default_factory=list)


class CommandParseResponse(ApiModel):
    """Parsed slash-command shape returned by the server.

    The agent-side slash-command parser (formerly ``molab.agent.skills.commands``)
    was deleted by the ``agent-pydanticai-rectification`` spec; this response
    schema is now the canonical shape and any future parser must produce it.
    """

    kind: Literal["skill", "builtin", "error"]
    name: str = ""
    skillId: str = ""
    parameters: dict[str, str] = Field(default_factory=dict)
    planMode: bool = False
    error: str = ""


class AgentSystemPromptResponse(ApiModel):
    """Per-session system prompt breakdown for the inspector."""

    base: str
    workspaceInstructions: str = ""
    skillInstructions: str = ""
    sessionOverride: str | None = None
    planMode: bool = False
    effective: str


class SkillResponse(ApiModel):
    """A saved skill (goal template + tool scope + system addendum)."""

    id: str
    name: str
    description: str = ""
    goalTemplate: str
    slashName: str = ""
    instructions: str = ""
    defaultPlanMode: bool = False
    constraints: list[str] = Field(default_factory=list)
    successCriteria: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    allowedTools: list[str] = Field(default_factory=list)
    deniedTools: list[str] = Field(default_factory=list)
    requiresExitTool: str = ""
    builtin: bool = False
    scope: str = "workspace"
    createdAt: str = ""
    updatedAt: str = ""


class SkillListResponse(ApiModel):
    skills: list[SkillResponse] = Field(default_factory=list)


class ToolParameterResponse(ApiModel):
    name: str
    annotation: str = "Any"
    required: bool = False


class AgentToolResponse(ApiModel):
    """One agent tool — molab **builtin** or MCP-discovered.

    ``source`` is:

    * ``"builtin"`` — always-on molab tools (``workspace_ensure``,
      ``run_land``, ``code_write``, …)
    * ``"mcp:<server-name>"`` — tool from an MCP server, so the UI can
      attach it to that server's expanded row
    """

    name: str
    description: str = ""
    parameters: list[ToolParameterResponse] = Field(default_factory=list)
    requiresApproval: bool = False
    source: str


class McpToolGroupResponse(ApiModel):
    """Per-server discovery status for the MCP server list.

    Even when a server is offline / misconfigured / unauthorized we want
    the UI to render *something* under that server's heading — a row with
    the error keeps users oriented instead of silently dropping the group.
    """

    server: str
    scope: Literal["user", "workspace"]
    ok: bool
    toolCount: int = 0
    error: str | None = None


class AgentToolListResponse(ApiModel):
    tools: list[AgentToolResponse] = Field(default_factory=list)
    mcpGroups: list[McpToolGroupResponse] = Field(default_factory=list)


class McpAuthSummary(ApiModel):
    """Public-safe view of a server's structured auth settings.

    Token values, refresh tokens, and client secrets are never exposed —
    only metadata the UI needs to render the connection card. ``connected``
    indicates the token store on disk has at least one persisted token
    (rough proxy for "user has completed Connect at least once").
    """

    type: Literal["oauth2"]
    scopes: list[str] = Field(default_factory=list)
    clientId: str | None = None
    connected: bool = False


class McpServerResponse(ApiModel):
    """One MCP server entry, possibly merged across scopes.

    ``shadowed`` is True when this entry exists at User scope but is
    overridden by a Workspace entry of the same name. ``unresolvedSecrets``
    lists ``${SECRET:KEY}`` references that have no value in either secret
    store — the runtime skips such entries.
    """

    name: str
    scope: Literal["native", "user", "workspace"]
    transport: str = ""
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    envKeys: list[str] = Field(default_factory=list)
    headerKeys: list[str] = Field(default_factory=list)
    secretRefs: list[str] = Field(default_factory=list)
    unresolvedSecrets: list[str] = Field(default_factory=list)
    shadowed: bool = False
    valid: bool = True
    invalidReason: str = ""
    auth: McpAuthSummary | None = None


class McpServerListResponse(ApiModel):
    """Merged view of both scopes plus the resolved file paths.

    ``workspacePath`` and ``userPath`` are the absolute paths the store
    would read/write at each scope (whether or not the file currently
    exists) — useful for UI tooltips like "Edit ~/.molab/mcp.json".
    """

    workspacePath: str
    userPath: str
    servers: list[McpServerResponse] = Field(default_factory=list)


class McpServerTestResponse(ApiModel):
    """Outcome of probing an MCP server (subprocess spawn or HTTP handshake)."""

    ok: bool
    name: str
    scope: Literal["native", "user", "workspace"]
    transport: str
    latencyMs: int = 0
    toolCount: int = 0
    error: str | None = None


class McpSecretRefRow(ApiModel):
    """One row in the secrets list — key + which servers reference it."""

    key: str
    isSet: bool
    referencedBy: list[str] = Field(default_factory=list)


class McpSecretListResponse(ApiModel):
    """Secrets at the requested scope. Plaintext values are never returned."""

    scope: Literal["native", "user", "workspace"]
    path: str
    secrets: list[McpSecretRefRow] = Field(default_factory=list)


class AgentHealthResponse(ApiModel):
    """Whether the agent runtime is ready to start a new session.

    ``ready=False`` indicates a configuration problem the user can
    resolve in Agent Settings (most commonly: no API key). ``source``
    is one of ``"stored"`` (workspace config), ``"env"`` (process env
    var), or ``"none"`` (not configured).
    """

    ready: bool = False
    provider: str = ""
    model: str = ""
    source: str = "none"
    reason: str = ""
    envVar: str = ""
