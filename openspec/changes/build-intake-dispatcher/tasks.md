## 1. Gateway schemas

- [x] 1.1 `gateway/schemas.py`: add `mutation_requested: bool = False`,
      `approval_required: bool = False`, `unsupported_reason: str | None
      = None` to `IntakeDecision`
- [x] 1.2 Update `IntakeDecision`'s docstring — `route`/`ready_to_route`
      are no longer inert for `compliance_check`

## 2. Dispatcher node

- [x] 2.1 `workflows/intake/nodes.py`: add `_ROUTE_TABLE` (static,
      intent-keyed, `compliance_check` only)
- [x] 2.2 `workflows/intake/nodes.py`: add `resolve_route(state) -> dict`
      — deterministic, no model call; passes through unchanged when
      `intent is None` (still needs clarification); resolves
      `compliance_check` to a real route; marks `provision`/`inquiry`
      `unsupported_reason` with `mutation_requested` set for `provision`
- [x] 2.3 `workflows/intake/graph.py`: wire
      `classify_workflow -> resolve_route -> END`

## 3. Harness

- [x] 3.1 `harness/core.py`: extend `_classify`'s `PlatformOpsEvent`
      payload with `route`/`ready_to_route`/`mutation_requested`/
      `approval_required`/`unsupported_reason`
- [x] 3.2 `harness/core.py`: correct the module docstring's "nothing
      downstream acts on it yet" / "resolve_route out of scope" framing

## 4. Tests

- [x] 4.1 `tests/workflows/intake/test_classify_workflow.py`: replace
      `test_route_and_ready_to_route_always_inert` with
      `test_compliance_check_resolves_a_real_route`,
      `test_provision_has_no_route_yet_and_is_marked_unsupported`,
      `test_inquiry_has_no_route_yet_and_is_marked_unsupported`,
      `test_pending_clarification_is_not_marked_unsupported`,
      `test_missing_tool_call_route_stays_inert_too`
- [x] 4.2 `tests/harness/test_core.py`: update the two hardcoded
      `event.payload == {"intent": ...}` assertions to the new payload
      shape

## 5. Docs

- [x] 5.1 `docs/INTAKE_HITL_ROUTING.md`: correct the `## Status` line and
      the `Intake workflow`/`Gateway schemas`/`Dispatcher` rows of the
      Real vs. Designed table, dated and noted as a correction
- [x] 5.2 `docs/HARNESS_DESIGN.md`: correct the document-map rows for
      `INTAKE_HITL_ROUTING.md`, `WORKFLOW_LIFECYCLE_PATTERN.md`, and
      `PLATFORMOPS_HARNESS.md` — all previously described a one-node
      graph with no dispatcher

## 6. Verify

- [x] 6.1 Run `tests/workflows/intake/` and `tests/harness/`; all pass
      with no real model credentials configured anywhere
- [ ] 6.2 `openspec validate build-intake-dispatcher --strict` passes
