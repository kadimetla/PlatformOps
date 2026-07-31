"""Group-to-approval-grant mapping.

This is deterministic auth-boundary code. It consumes group names that
were already verified as part of an authenticated OIDC session and
turns configured PlatformOps approval groups into approval grants.

It deliberately does not mint ExecutionGrants. Per
ACCESS_POLICY_AND_IAM_DISCOVERY.md's precedence rule, execution grants
come from provider discovery only, never from a second PlatformOps YAML
mapping.
"""
from pydantic import BaseModel, Field, model_validator

from gateway.auth.schemas import ApprovalGrant, Capability, ExecutionGrant
from gateway.schemas import Scope


class GroupGrantMapping(BaseModel):
    group: str
    grant_type: str = "approval"
    scope: Scope
    capability: Capability

    @model_validator(mode="after")
    def only_approval_mappings_are_supported(self) -> "GroupGrantMapping":
        if self.grant_type != "approval":
            raise ValueError(
                "IdP group mappings may only create approval grants; "
                "execution grants must come from provider discovery"
            )
        return self


class GrantMappingConfig(BaseModel):
    mappings: list[GroupGrantMapping] = Field(default_factory=list)


class GrantResolution(BaseModel):
    execution_grants: list[ExecutionGrant] = Field(default_factory=list)
    approval_grants: list[ApprovalGrant] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


def resolve_group_grants(
    groups: list[str], config: GrantMappingConfig
) -> GrantResolution:
    """Resolve direct group membership to approval grants.

    This intentionally performs exact group-name matching only. Group
    inheritance/transitive membership belongs in the IdP or provider
    discovery layer, not in this local mapping function.
    """
    group_set = set(groups)
    result = GrantResolution()

    for mapping in config.mappings:
        if mapping.group not in group_set:
            continue

        result.approval_grants.append(
            ApprovalGrant(scope=mapping.scope, max_capability=mapping.capability)
        )

        result.evidence.append(
            f"group {mapping.group!r} resolved to approval grant for "
            f"{mapping.scope.org_bu}/"
            f"{mapping.scope.project or '*'}/{mapping.scope.workspace or '*'}"
        )

    return result
