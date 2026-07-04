"""Core data schemas for the PlatformOps Gateway spike.

These turn the prompt-level procedure the ADK agents already follow into
records the dispatcher can check deterministically. See
docs/harness_deep_dive.md for the design narrative behind each schema and
docs/HARNESS_DESIGN.md for how this fits the overall harness.
"""
import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RequestEnvelope(BaseModel):
    request_id: str = Field(..., description="Unique UUID for the request")
    org_id: str = Field(..., description="Target Tenant Organization ID")
    bu_id: str = Field(..., description="Target Business Unit ID")
    channel: str = Field(..., description="Origin channel: 'slack', 'teams', 'webhook', 'cli'")
    channel_user_id: str = Field(..., description="Raw identifier of the user in the channel")
    workspace_id: str = Field(..., description="Target workspace bundle identifier")
    raw_payload: str = Field(..., description="Raw YAML spec or command string submitted by user")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context info")


class WorkspaceBundle(BaseModel):
    bundle_id: str = Field(..., description="Unique configuration bundle slug, e.g. 'acme-payments'")
    aws_region: str = Field(default="us-east-1")
    aws_profile: str = Field(default="platformops-sandbox")
    cost_ceiling_usd: float = Field(default=5.0)
    allowed_resource_types: list[str] = Field(..., description="Resource types (CFN style) allowed")
    tfe_workspace: Optional[str] = Field(None, description="HCP Terraform workspace name (if toolchain=terraform)")
    enable_tf_operations: bool = Field(default=False, description="Operator-controlled toggle for tf apply")
    model_overrides: Dict[str, str] = Field(
        default_factory=dict,
        description="Override default models in config/models.yaml per role",
    )


class PlanRecord(BaseModel):
    plan_id: str = Field(..., description="Plan identifier")
    request_id: str = Field(..., description="Reference to the parent RequestEnvelope")
    toolchain: str = Field(..., description="'cdk' or 'terraform'")
    plan_text: str = Field(..., description="The raw plan or synthesized CloudFormation/Terraform layout")
    plan_hash: str = Field(..., description="SHA256 hash of plan_text for tamper-resistance")
    vibe_diff: str = Field(..., description="Plain-English summary of changes proposed")
    estimated_monthly_cost: float = Field(default=0.0)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class ApprovalRecord(BaseModel):
    approval_id: str = Field(..., description="Approval record identifier")
    plan_id: str = Field(..., description="Target PlanRecord ID")
    plan_hash: str = Field(..., description="Must match the PlanRecord hash at verification time")
    agent_approved: bool = Field(default=False)
    agent_reasoning: str = Field(..., description="Explanation from security_agent")
    human_approved: bool = Field(default=False)
    human_reviewer: Optional[str] = Field(None, description="User identifier who approved via Control UI")
    approval_timestamp: Optional[datetime.datetime] = None
    is_valid: bool = Field(default=True, description="True if not expired or manually invalidated")


class ToolIntent(BaseModel):
    """A single planned mutating cloud operation, proposed by a provisioning
    sub-agent (cdk_provisioning_agent or terraform_provisioning_agent) and
    checked by BrokeredToolDispatcher before it's allowed to execute."""

    intent_id: str
    plan_id: str
    plan_hash: str
    org_id: str
    bu_id: str
    resource_type: str = Field(..., description="CloudFormation-style type, e.g. 'AWS::S3::Bucket'")
    resource_identifier: str
    operation: str = Field(..., description="'CreateResource', 'UpdateResource', or 'DeleteResource'")
    region: str
    estimated_monthly_cost: float
    payload: Dict[str, Any] = Field(default_factory=dict)
