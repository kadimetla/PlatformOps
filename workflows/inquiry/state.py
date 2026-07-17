"""Graph state and boundary models for the inquiry workflow (renamed
from workflows/discovery/ on 2026-07-17 -- see
openspec/changes/build-discovery-workflow/design.md's "Renamed to
workflows/inquiry/" note for why). See design.md's Decisions --
InquiryQuery/InquiryResult are new, explicit models, not a reuse of
InfraInventoryRecord directly: a query needs a lookup key, a result
needs an explicit found: bool a bare record can't represent.
"""
from typing import Optional, TypedDict

from pydantic import BaseModel

from gateway.schemas import InfraInventoryRecord, WorkspaceBundle


class InquiryQuery(BaseModel):
    """org_id/bu_id are assumed already resolved from the authenticated
    session -- never parsed from resource_type_description or any other
    free-text field (docs/intent_routing_and_staged_confirmation.md
    Part A)."""

    org_id: str
    bu_id: str
    resource_identifier: str
    resource_type: Optional[str] = None
    resource_type_description: Optional[str] = None


class InquiryResult(BaseModel):
    """resource_type is always populated on a resolved lookup (whether
    given directly or classified) so a caller can show the
    interpretation alongside the answer, in one response -- Part D's
    "show, don't block" confirmation weight, realized as a field rather
    than a separate pause step."""

    found: bool = False
    resource_type: Optional[str] = None
    resource_identifier: str
    record: Optional[InfraInventoryRecord] = None
    clarifying_question: Optional[str] = None


class InquiryState(TypedDict):
    query: InquiryQuery
    bundle: WorkspaceBundle
    resolved_resource_type: Optional[str]
    clarifying_question: Optional[str]
    result: Optional[InquiryResult]
