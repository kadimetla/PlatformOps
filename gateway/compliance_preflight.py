"""Compliance preflight and spec-shape validation -- extracted from
gateway/plan_request.py at cutover (openspec/changes/migrate-to-langgraph/
tasks.md task 6.1) so both gateway/plan_request.py (a thin re-export
after cutover) and workflows/drafting/plan_request.py (the real
implementation) can import these without a circular import between
them. Framework-independent -- no ADK, no LangGraph, touches neither.
"""
from typing import Any

from spec.check_compliance import check_compliance

REQUIRED_SPEC_KEYS = {"app_name", "region", "resources"}


class ComplianceError(Exception):
    """Raised when a request's spec fails spec/check_compliance.py's
    deterministic rules. Carries the exact failure reasons."""

    def __init__(self, failures: list[str]):
        self.failures = failures
        super().__init__("; ".join(failures))


def is_valid_spec_shape(candidate: Any) -> bool:
    """Deterministic schema check against spec/example_submission.yaml's
    shape -- required top-level keys, resources is a list of dicts each
    with a 'type'. No LLM judgment involved."""
    if not isinstance(candidate, dict):
        return False
    if not REQUIRED_SPEC_KEYS.issubset(candidate.keys()):
        return False
    resources = candidate.get("resources")
    if not isinstance(resources, list):
        return False
    return all(isinstance(r, dict) and "type" in r for r in resources)


def run_compliance_preflight(spec: dict) -> None:
    """Mandatory gate: raises ComplianceError on any failure, never
    invoked optionally."""
    failures = check_compliance(spec)
    if failures:
        raise ComplianceError(failures)
