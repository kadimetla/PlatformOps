"""The effective_access invariant. See
docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md's "The effective_access
Invariant":

    effective_access = min(actor.execution_grants[...], org_bu_policy.ceiling[...])

Deny by default in both halves: no matching execution grant resolves
to Capability.NONE, no matching ceiling entry also resolves to
Capability.NONE -- an unconfigured scope is never treated as
unrestricted.

Scope matching assumption, stated because no doc pins this down
(AGENTS.md: state assumptions, don't guess silently): "*" in a stored
Scope's project/workspace means "matches any"; org/bu are always exact.
When multiple entries match a query, the most specific one wins (exact
project+workspace beats a wildcard on either) rather than the
highest-capability one -- picking the highest would let an unrelated
wildcard grant leak capability into a more specific scope, which is
the opposite of deny-by-default.

Tie-break when two entries share the *same* specificity, stated
explicitly rather than left to dict/YAML/list ordering:
- Execution grants: choose the LOWER capability. Two equally-specific
  grants disagreeing on capability should never resolve to the more
  permissive one -- same deny-by-default logic as effective_access
  itself, applied one level down.
- Policy ceilings: this is a config-authoring bug, not a runtime
  condition to silently resolve either way -- raise, don't guess.
"""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.schemas import Intent, Scope


class CeilingEntry(BaseModel):
    scope: Scope
    intent: Intent
    ceiling: Capability


class OrgBuPolicyConfig(BaseModel):
    entries: list[CeilingEntry] = Field(default_factory=list)


def _specificity(scope: Scope) -> int:
    return (scope.project not in (None, "*")) + (scope.workspace not in (None, "*"))


def _scope_matches(entry_scope: Scope, query_scope: Scope) -> bool:
    if entry_scope.org != query_scope.org or entry_scope.bu != query_scope.bu:
        return False
    if entry_scope.project not in (None, "*", query_scope.project):
        return False
    if entry_scope.workspace not in (None, "*", query_scope.workspace):
        return False
    return True


def resolve_execution_capability(
    scope: Scope, grants: list[ExecutionGrant]
) -> Capability:
    """The WHO half: best-match execution grant for this scope, or
    Capability.NONE if none matches. Same-specificity ties resolve to
    the lower capability -- see module docstring."""

    matches = [g for g in grants if _scope_matches(g.scope, scope)]
    if not matches:
        return Capability.NONE
    top = max(_specificity(g.scope) for g in matches)
    tied = [g for g in matches if _specificity(g.scope) == top]
    return min(g.capability for g in tied)


def resolve_ceiling(scope: Scope, intent: Intent, config: OrgBuPolicyConfig) -> Capability:
    """The WHAT half: best-match policy ceiling for this
    (scope, intent), or Capability.NONE if none is configured. Raises
    if same-specificity entries disagree on the ceiling -- see module
    docstring."""

    matches = [
        e for e in config.entries if e.intent == intent and _scope_matches(e.scope, scope)
    ]
    if not matches:
        return Capability.NONE
    top = max(_specificity(e.scope) for e in matches)
    tied = [e for e in matches if _specificity(e.scope) == top]
    ceilings = {e.ceiling for e in tied}
    if len(ceilings) > 1:
        raise ValueError(
            f"ambiguous policy ceiling for scope={scope!r} intent={intent!r}: "
            f"equally-specific entries disagree ({sorted(c.value for c in ceilings)}) "
            "-- fix the policy config, this is an authoring bug"
        )
    return tied[0].ceiling


def effective_access(
    scope: Scope,
    intent: Intent,
    execution_grants: list[ExecutionGrant],
    policy: OrgBuPolicyConfig,
) -> Capability:
    grant = resolve_execution_capability(scope, execution_grants)
    ceiling = resolve_ceiling(scope, intent, policy)
    return min(grant, ceiling)


def load_org_bu_policy(path: Path | None) -> OrgBuPolicyConfig:
    if path is None:
        return OrgBuPolicyConfig()
    data = yaml.safe_load(path.read_text()) or {}
    return OrgBuPolicyConfig.model_validate(data)
