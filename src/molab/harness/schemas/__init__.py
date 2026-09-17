"""Frozen pydantic schemas for ``molab.harness``.

Pure data: every model has ``frozen=True``. Discriminator fields are
``typing.Literal[...]`` aliases, not ``enum.Enum``, matching the workspace
convention.
"""

from __future__ import annotations

from molab.harness.schemas.agent_call import AgentCallResult, AgentCallSpec
from molab.harness.schemas.approval import (
    ApprovalDecision,
    ApprovalIntent,
    ApprovalRequest,
    ApprovalScope,
)
from molab.harness.schemas.artifact import (
    WELL_KNOWN_ARTIFACT_KINDS,
    ArtifactKind,
    PlanArtifactRef,
)
from molab.harness.schemas.audit_report import AuditReport
from molab.harness.schemas.bound_workflow import (
    BoundTask,
    BoundWorkflow,
    ExecutionEnvironment,
    ResourcePolicy,
)
from molab.harness.schemas.capability import ToolCapability
from molab.harness.schemas.capability_invocation import CapabilityInvocationResult
from molab.harness.schemas.capability_selection import (
    CapabilitySelection,
    SelectedCapability,
)
from molab.harness.schemas.change_proposal import (
    CHANGE_PROPOSAL_KIND,
    AgentIntent,
    ApprovalLevel,
    ChangeProposal,
    ChangeSpec,
    HighRiskOp,
    ObjectRef,
    ProposalOutcome,
    ProposalStatus,
    Reversibility,
    StateSnapshot,
)
from molab.harness.schemas.command import CommandResult, CommandSpec
from molab.harness.schemas.event import EventType, HarnessEvent
from molab.harness.schemas.execution_report import ExecutionReport
from molab.harness.schemas.execution_result import ExecutionResult
from molab.harness.schemas.experiment_report import ExperimentReport
from molab.harness.schemas.experiment_spec import (
    ExperimentSpec,
    ResolvedQuestion,
    SpecCondition,
    SpecVariable,
)
from molab.harness.schemas.final_report import FinalReport
from molab.harness.schemas.input_set import InputSet, SweepAxis, SweepStrategy
from molab.harness.schemas.intervention import BlockedTask, InterventionRequest
from molab.harness.schemas.mode_result import ModeResult, StageTiming
from molab.harness.schemas.parameter import ParameterSource, ParameterValue
from molab.harness.schemas.plan_review import PlanReview, PlanReviewFinding
from molab.harness.schemas.policy import ApprovalPolicy, PathPolicy, ToolPolicy
from molab.harness.schemas.step_audit import (
    FindingResolution,
    FormArtifactRefField,
    FormBooleanField,
    FormDocument,
    FormField,
    FormKeyValueField,
    FormMarkdownField,
    FormMultiSelectField,
    FormNumberField,
    FormSelectField,
    FormSelectOption,
    FormTableColumn,
    FormTableField,
    FormTextAreaField,
    FormTextField,
    ReviewDecision,
    ReviewFinding,
    ReviewPack,
    StepAuditPolicy,
    approval_decision_to_review,
    review_decision_to_approval,
)
from molab.harness.schemas.test_source import TestSource
from molab.harness.schemas.test_spec import (
    TestKind,
    TestResult,
    TestSpec,
    TestSpecBundle,
    TestStatus,
)
from molab.harness.schemas.user_plan import UserPlan
from molab.harness.schemas.validation import PlanValidationReport, ValidationViolation
from molab.harness.schemas.workflow_ir import (
    DependencyEdge,
    ExpectedOutput,
    PlanTaskIR,
    PlanWorkflowIR,
)
from molab.harness.schemas.workflow_source import GeneratedFile, WorkflowSource

__all__ = [
    # ChangeProposal / AgentIntent — high-risk-mutation guard (integration P0.5)
    "CHANGE_PROPOSAL_KIND",
    "WELL_KNOWN_ARTIFACT_KINDS",
    "AgentCallResult",
    "AgentCallSpec",
    "AgentIntent",
    "ApprovalDecision",
    "ApprovalIntent",
    "ApprovalLevel",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalScope",
    "ArtifactKind",
    "AuditReport",
    "BlockedTask",
    "BoundTask",
    "BoundWorkflow",
    "CapabilityInvocationResult",
    "CapabilitySelection",
    "ChangeProposal",
    "ChangeSpec",
    "CommandResult",
    "CommandSpec",
    "DependencyEdge",
    "EventType",
    "ExecutionEnvironment",
    "ExecutionReport",
    "ExecutionResult",
    "ExpectedOutput",
    "ExperimentReport",
    "ExperimentSpec",
    "FinalReport",
    "FindingResolution",
    "FormArtifactRefField",
    "FormBooleanField",
    "FormDocument",
    "FormField",
    "FormKeyValueField",
    "FormMarkdownField",
    "FormMultiSelectField",
    "FormNumberField",
    "FormSelectField",
    "FormSelectOption",
    "FormTableColumn",
    "FormTableField",
    "FormTextAreaField",
    "FormTextField",
    "GeneratedFile",
    "HarnessEvent",
    "HighRiskOp",
    "InputSet",
    "InterventionRequest",
    "ModeResult",
    "ObjectRef",
    "ParameterSource",
    "ParameterValue",
    "PathPolicy",
    "PlanArtifactRef",
    "PlanReview",
    "PlanReviewFinding",
    "PlanTaskIR",
    "PlanValidationReport",
    "PlanWorkflowIR",
    "ProposalOutcome",
    "ProposalStatus",
    "ResolvedQuestion",
    "ResourcePolicy",
    "Reversibility",
    "ReviewDecision",
    "ReviewFinding",
    "ReviewPack",
    "SelectedCapability",
    "SpecCondition",
    "SpecVariable",
    "StageTiming",
    "StateSnapshot",
    "StepAuditPolicy",
    "SweepAxis",
    "SweepStrategy",
    "TestKind",
    "TestResult",
    "TestSource",
    "TestSpec",
    "TestSpecBundle",
    "TestStatus",
    "ToolCapability",
    "ToolPolicy",
    "UserPlan",
    "ValidationViolation",
    "WorkflowSource",
    "approval_decision_to_review",
    "review_decision_to_approval",
]
