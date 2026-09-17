"""Concrete :class:`molab.harness.Stage` subclasses for the §3 pipeline.

Each stage is a thin wrapper that constructs typed inputs, drives the right
artifact-store / agent-gateway call, and returns a single
:class:`PlanArtifactRef`. The audit bracket
(:func:`~molab.harness.core.stage_runner.run_stage_bracketed`) handles
event emission and artifact-lineage wiring around them.
"""

from __future__ import annotations

from molab.harness.stages.approval_gate import ApprovalGate, Approver, auto_grant_approver
from molab.harness.stages.assemble_knowledge_context import AssembleKnowledgeContext
from molab.harness.stages.bind_molcrafts_tasks import BindMolcraftsTasks
from molab.harness.stages.compile_workflow import CompileWorkflow
from molab.harness.stages.evidence import (
    CapabilityGap,
    Diagnosis,
    collect_evidence_text,
    diagnose_failure,
)
from molab.harness.stages.execute_tests import ExecuteTests
from molab.harness.stages.execute_workflow import ExecuteWorkflow
from molab.harness.stages.extract_workflow_ir import ExtractWorkflowIR
from molab.harness.stages.generate_audit_report import GenerateAuditReport
from molab.harness.stages.generate_execution_report import GenerateExecutionReport
from molab.harness.stages.generate_experiment_report import GenerateExperimentReport
from molab.harness.stages.generate_experiment_spec import GenerateExperimentSpec
from molab.harness.stages.generate_final_report import GenerateFinalReport
from molab.harness.stages.generate_input_set import GenerateInputSet
from molab.harness.stages.generate_test_code import GenerateTestCode
from molab.harness.stages.generate_test_spec import GenerateTestSpec
from molab.harness.stages.generate_workflow_source import GenerateWorkflowSource
from molab.harness.stages.invoke_capability import InvokeCapability
from molab.harness.stages.materialize_and_execute_tests import MaterializeAndExecuteTests
from molab.harness.stages.materialize_execution import MaterializeExecution
from molab.harness.stages.realize_board import RealizeBoard
from molab.harness.stages.resolve_capabilities import ResolveCapabilities
from molab.harness.stages.review_plan import ReviewPlan
from molab.harness.stages.save_user_plan import SaveUserPlan
from molab.harness.stages.step_audit_loop import StepAuditLoop
from molab.harness.stages.validate_bound_workflow import ValidateBoundWorkflow
from molab.harness.stages.validate_experiment_spec import ValidateExperimentSpec
from molab.harness.stages.validate_input_set import ValidateInputSet
from molab.harness.stages.validate_test_source import ValidateTestSource
from molab.harness.stages.validate_test_spec import ValidateTestSpec
from molab.harness.stages.validate_workflow_ir import ValidateWorkflowIR
from molab.harness.stages.validate_workflow_source import ValidateWorkflowSource

__all__ = [
    "ApprovalGate",
    "Approver",
    "AssembleKnowledgeContext",
    "BindMolcraftsTasks",
    "CapabilityGap",
    "CompileWorkflow",
    "Diagnosis",
    "ExecuteTests",
    "ExecuteWorkflow",
    "ExtractWorkflowIR",
    "GenerateAuditReport",
    "GenerateExecutionReport",
    "GenerateExperimentReport",
    "GenerateExperimentSpec",
    "GenerateFinalReport",
    "GenerateInputSet",
    "GenerateTestCode",
    "GenerateTestSpec",
    "GenerateWorkflowSource",
    "InvokeCapability",
    "MaterializeAndExecuteTests",
    "MaterializeExecution",
    "RealizeBoard",
    "ResolveCapabilities",
    "ReviewPlan",
    "SaveUserPlan",
    "StepAuditLoop",
    "ValidateBoundWorkflow",
    "ValidateExperimentSpec",
    "ValidateInputSet",
    "ValidateTestSource",
    "ValidateTestSpec",
    "ValidateWorkflowIR",
    "ValidateWorkflowSource",
    "auto_grant_approver",
    "collect_evidence_text",
    "diagnose_failure",
]
