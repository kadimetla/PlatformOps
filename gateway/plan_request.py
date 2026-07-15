"""plan_request(envelope) -- CUT OVER (2026-07-14,
openspec/changes/migrate-to-langgraph/tasks.md task 6.1) to the
LangGraph-based implementation in workflows/drafting/plan_request.py.
This module is now a thin re-export preserving the exact same public
API (`from gateway.plan_request import plan_request` and friends keep
working unchanged) so callers and the existing test suite don't need
to change anything.

ComplianceError/is_valid_spec_shape/run_compliance_preflight/
REQUIRED_SPEC_KEYS moved to gateway/compliance_preflight.py at the same
cutover, specifically to avoid a circular import: workflows/drafting/
plan_request.py needs those, and this module needs plan_request FROM
workflows/drafting/plan_request.py -- both modules importing from a
third, dependency-free module breaks the cycle cleanly rather than
relying on Python's fragile "define shared stuff before the circular
import line" import-order behavior.

agents/*.py and the ADK-based implementation this module used to
contain are no longer on the active import path (task 6.2) but are not
yet deleted (task 7.1 does that, after one release cycle with no
regressions -- see design.md's Migration Plan and Rollback).
"""
from gateway.compliance_preflight import (
    REQUIRED_SPEC_KEYS,
    ComplianceError,
    is_valid_spec_shape,
    run_compliance_preflight,
)
from workflows.drafting.plan_request import (
    envelope_to_spec,
    extract_spec_from_free_text,
    plan_request,
)

__all__ = [
    "REQUIRED_SPEC_KEYS",
    "ComplianceError",
    "is_valid_spec_shape",
    "run_compliance_preflight",
    "envelope_to_spec",
    "extract_spec_from_free_text",
    "plan_request",
]
