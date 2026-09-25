"""Temporary edge-only normalization of legacy workspace scope hints."""
from enum import Enum

from pydantic import BaseModel, ConfigDict

from gateway.resource_scope_registry import LegacyResourceScopeEdgeLookup
from gateway.schemas import ScopeHint


class LegacyScopeNormalizationStatus(str, Enum):
    RESOLVED = "resolved"
    NON_ROUTABLE = "non_routable"


class LegacyScopeNormalization(BaseModel):
    """Only the modern durable identifier crosses this compatibility boundary."""

    model_config = ConfigDict(extra="forbid")

    status: LegacyScopeNormalizationStatus
    scope_id: str | None = None


def normalize_legacy_scope_hint(
    hint: ScopeHint, lookup: LegacyResourceScopeEdgeLookup,
) -> LegacyScopeNormalization:
    """Map old workspace text to `env` only for one unambiguous active scope."""
    if hint.project is None or hint.workspace is None:
        return LegacyScopeNormalization(status=LegacyScopeNormalizationStatus.NON_ROUTABLE)
    matches = lookup.find_active_by_legacy_segments(
        organization_slug=hint.tenant.org,
        business_unit_slug=hint.tenant.bu,
        project_slug=hint.project,
        environment_slug=hint.workspace,
    )
    if len(matches) != 1:
        return LegacyScopeNormalization(status=LegacyScopeNormalizationStatus.NON_ROUTABLE)
    return LegacyScopeNormalization(
        status=LegacyScopeNormalizationStatus.RESOLVED,
        scope_id=matches[0].scope_id,
    )
