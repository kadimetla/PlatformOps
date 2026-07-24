"""Graph state and boundary models for the intake workflow. See
openspec/changes/build-intake-workflow/design.md's Decisions --
IntakeRequest/IntakeResult are new, explicit models, not a reuse of
RequestEnvelope/InquiryQuery: an intake request needs raw text plus
already-resolved identity, an intake result needs either a resolved
hint or a clarifying question, neither of which any existing model
shape represents.
"""
from typing import Optional, TypedDict

from pydantic import BaseModel


class IntakeRequest(BaseModel):
    """org_id/bu_id are assumed already resolved from the authenticated
    session -- never parsed from raw_text
    (docs/intent_routing_and_staged_confirmation.md Part A)."""

    org_id: str
    bu_id: str
    raw_text: str


class IntakeResult(BaseModel):
    workflow_hint: Optional[str] = None  # "drafting" | "inquiry"
    clarifying_question: Optional[str] = None


class IntakeState(TypedDict):
    request: IntakeRequest
    result: Optional[IntakeResult]
