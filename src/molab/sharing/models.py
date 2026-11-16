"""Version-one sharing contracts. Private workspace responses are never accepted."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from molab.workspace.models import RunStatus

Identifier = Annotated[
    str, Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
]
Title = Annotated[str, Field(min_length=1, max_length=200)]
Parameter = StrictStr | StrictBool | StrictInt | StrictFloat | None


class SharingModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, hide_input_in_errors=True
    )


class Principal(SharingModel):
    id: str
    issuer: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    display_name: Title
    disabled: bool = False


class PublishedProject(SharingModel):
    id: Identifier
    name: Title
    description: str = Field(default="", max_length=10000)


class PublishedExperiment(PublishedProject):
    pass


class ScalarPoint(SharingModel):
    value: StrictFloat | StrictInt
    step: StrictFloat | StrictInt | None = None


class PublishedRun(SharingModel):
    id: Identifier
    experiment_id: Identifier
    name: Title
    status: RunStatus
    parameters: dict[Title, Parameter] = Field(default_factory=dict, max_length=50)
    metrics: dict[Title, Annotated[list[ScalarPoint], Field(max_length=2000)]] = Field(
        default_factory=dict, max_length=20
    )


class BeginPublication(SharingModel):
    schema_version: Literal[1] = 1
    workspace_id: Identifier
    project: PublishedProject
    base_version: str | None = None
    activate: bool = False


class PublicationBatch(SharingModel):
    experiments: list[PublishedExperiment] = Field(default_factory=list, max_length=500)
    runs: list[PublishedRun] = Field(default_factory=list, max_length=500)


class InvitationRequest(SharingModel):
    recipient_id: Identifier
    role: Literal["viewer"] = "viewer"


class PublicationSelection(SharingModel):
    """Owner-approved object/field selection; refresh never expands these lists."""

    project_id: Identifier
    experiment_ids: list[Identifier] = Field(default_factory=list, max_length=500)
    # Run ids can repeat across experiments. Use the canonical compound ref.
    run_refs: list[str] = Field(default_factory=list, max_length=10000)
    parameter_keys: list[Title] = Field(default_factory=list, max_length=50)
    metric_keys: list[Title] = Field(default_factory=list, max_length=20)
    include_descriptions: bool = False


class PublicationPreview(SharingModel):
    schema_version: Literal[1] = 1
    workspace_id: Identifier
    project: PublishedProject
    experiments: list[PublishedExperiment]
    runs: list[PublishedRun]


class PublishRequest(SharingModel):
    selection: PublicationSelection
    preview_digest: str


class ApprovedPublication(SharingModel):
    source_id: str
    workspace_id: str
    shared_project_id: str
    selection: PublicationSelection
    last_digest: str


class SharedProject(SharingModel):
    id: str
    project: PublishedProject | None
    owner_id: str
    owner_name: str
    role: Literal["owner", "viewer"]
    active: bool
    version_id: str | None
    published_at: str | None
    source_seen_at: str | None


class SharedPage[Item](SharingModel):
    items: list[Item]
    total: int
    version_id: str | None = None


class Invitation(SharingModel):
    id: str
    project_id: str
    recipient_id: str
    created_by: str
    status: Literal["pending", "accepted", "declined", "revoked"]
    created_at: str
    expires_at: str
    project_name: str | None = None
    owner_name: str | None = None


class SharedMember(SharingModel):
    project_id: str
    principal_id: str
    role: Literal["viewer"]
    created_at: str
    revoked_at: str | None
    display_name: str


class ProjectMembers(SharingModel):
    members: list[SharedMember]
    invitations: list[Invitation]


class PublicationReceipt(SharingModel):
    project_id: str
    version_id: str


class PreviewResponse(SharingModel):
    preview: PublicationPreview
    digest: str


class InventoryRun(SharingModel):
    ref: str
    name: str
    parameter_keys: list[str]


class InventoryExperiment(SharingModel):
    id: str
    name: str
    runs: list[InventoryRun]


class InventoryProject(SharingModel):
    id: str
    name: str
    experiments: list[InventoryExperiment]


class AssetShareRequest(SharingModel):
    project_id: Identifier
    asset_id: Identifier
    recipient_id: Identifier
    # The owner must approve the registered bytes, even if a slot was replaced.
    digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class AssetInventoryItem(SharingModel):
    id: Identifier
    title: Title
    digest: str
    size: int = Field(ge=0)
    kind: Literal["file", "directory"]


class PrepareAssetShare(SharingModel):
    workspace_id: Identifier
    project_id: Identifier
    asset_id: Identifier
    recipient_id: Identifier
    title: Title
    digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    size: int = Field(ge=0)
    storage_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssetShare(SharingModel):
    id: Identifier
    project_id: Identifier
    asset_id: Identifier
    recipient_id: Identifier
    title: Title
    digest: str
    size: int
    state: Literal["preparing", "active", "revoking", "revoked"]
    created_at: str
    updated_at: str


class AssetTransfer(AssetShare):
    """Worker-only locator, derived from provisioned cluster identity bindings."""

    owner_uid: int = Field(ge=1)
    recipient_uid: int = Field(ge=1)
    cluster_id: str = Field(min_length=1, max_length=500)
    storage_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class AssetSharingCapabilities(SharingModel):
    enabled: bool
    backend: Literal["auto", "posix", "nfsv4", "group"] | None = None
    group_id: int | None = None
    file_only: bool = True
