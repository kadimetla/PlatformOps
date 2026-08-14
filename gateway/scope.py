"""Deterministic per-run scope parsing and resolution.

The resolver never asks an LLM to invent a tenant or workspace. Unknown
and unauthorized exact targets deliberately produce the same public result.
"""
from enum import Enum

from pydantic import BaseModel, model_validator

from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.policy.ceiling import resolve_execution_capability
from gateway.schemas import ClarificationQuestion, Scope, ScopeHint, TenantRef


class ScopeResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNAVAILABLE = "unavailable"


class ScopeResolution(BaseModel):
    status: ScopeResolutionStatus
    scope: Scope | None = None
    clarification: ClarificationQuestion | None = None
    public_reason: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ScopeResolution":
        if self.status == ScopeResolutionStatus.RESOLVED and self.scope is None:
            raise ValueError("resolved scope requires scope")
        if (
            self.status == ScopeResolutionStatus.CLARIFICATION_REQUIRED
            and self.clarification is None
        ):
            raise ValueError("clarification-required scope needs a question")
        if self.status == ScopeResolutionStatus.UNAVAILABLE and not self.public_reason:
            raise ValueError("unavailable scope requires a public reason")
        return self


def parse_scope_hint(value: str) -> ScopeHint:
    """Parse the canonical CLI form: ``org:bu/project/workspace``."""

    parts = value.split("/")
    if len(parts) != 3 or any(not part for part in parts):
        raise ValueError("scope must use org:bu/project/workspace")
    tenant, project, workspace = parts
    tenant_parts = tenant.split(":")
    if len(tenant_parts) != 2 or any(not part for part in tenant_parts):
        raise ValueError("scope tenant must use org:bu")
    return ScopeHint(
        tenant=TenantRef(org=tenant_parts[0], bu=tenant_parts[1]),
        project=project,
        workspace=workspace,
    )


def resolve_scope(
    hint: ScopeHint,
    known_workspaces: list[Scope],
    execution_grants: list[ExecutionGrant],
) -> ScopeResolution:
    """Resolve an exact, accessible workspace or request missing fields."""

    if hint.project is None or hint.workspace is None:
        return ScopeResolution(
            status=ScopeResolutionStatus.CLARIFICATION_REQUIRED,
            clarification=ClarificationQuestion(
                field="scope",
                question="Select the project and workspace for this request.",
                choices=[],
            ),
        )

    requested = Scope(
        org=hint.tenant.org,
        bu=hint.tenant.bu,
        project=hint.project,
        workspace=hint.workspace,
    )
    exists = any(candidate == requested for candidate in known_workspaces)
    capability = resolve_execution_capability(requested, execution_grants)
    if not exists or capability == Capability.NONE:
        return ScopeResolution(
            status=ScopeResolutionStatus.UNAVAILABLE,
            public_reason="target not found or not accessible",
        )

    return ScopeResolution(status=ScopeResolutionStatus.RESOLVED, scope=requested)
