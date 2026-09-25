"""Deterministic seals for a non-mutating provision plan and its approval."""
from hashlib import sha256
import hmac
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gateway.resolved_resource_scope import ResolvedResourceScopeContext


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


class TrustedProvisionPolicy(BaseModel):
    """Versioned profile policy selected by trusted workflow configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    version: int = Field(ge=1)

    @property
    def policy_digest(self) -> str:
        return _digest({"profile_id": self.profile_id, "version": self.version})


class ProvisionPlanInputs(BaseModel):
    """Typed string inputs from preflight; not cloud execution instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    values: dict[str, str] = Field(min_length=1)


class SealedProvisionPlan(BaseModel):
    """Immutable non-mutating plan snapshot that requires a matching approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    context: ResolvedResourceScopeContext
    policy: TrustedProvisionPolicy
    inputs: ProvisionPlanInputs
    plan_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    approval_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def seal(
        cls, *, context: ResolvedResourceScopeContext, policy: TrustedProvisionPolicy,
        inputs: ProvisionPlanInputs,
    ) -> "SealedProvisionPlan":
        plan_digest, approval_digest = _sealed_digests(context, policy, inputs)
        return cls(
            context=context, policy=policy, inputs=inputs, plan_digest=plan_digest,
            approval_digest=approval_digest,
        )

    @model_validator(mode="after")
    def _validate_digests(self) -> "SealedProvisionPlan":
        expected_plan, expected_approval = _sealed_digests(self.context, self.policy, self.inputs)
        if self.plan_digest != expected_plan or self.approval_digest != expected_approval:
            raise ValueError("plan or approval digest does not match sealed inputs, policy, and context")
        return self


class ProvisionApprovalDigest(BaseModel):
    """Minimal approval binding; actor and checkpoint evidence arrive in task 3.3."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    approval_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def for_plan(cls, plan: SealedProvisionPlan) -> "ProvisionApprovalDigest":
        return cls(plan_digest=plan.plan_digest, approval_digest=plan.approval_digest)

    def matches(self, plan: SealedProvisionPlan) -> bool:
        return (
            hmac.compare_digest(self.plan_digest, plan.plan_digest)
            and hmac.compare_digest(self.approval_digest, plan.approval_digest)
        )


def _sealed_digests(
    context: ResolvedResourceScopeContext, policy: TrustedProvisionPolicy, inputs: ProvisionPlanInputs,
) -> tuple[str, str]:
    plan_digest = _digest({
        "context_digest": context.resolution_digest,
        "policy_digest": policy.policy_digest,
        "inputs": inputs.values,
    })
    approval_digest = _digest({
        "context_digest": context.resolution_digest,
        "policy_digest": policy.policy_digest,
        "plan_digest": plan_digest,
    })
    return plan_digest, approval_digest
