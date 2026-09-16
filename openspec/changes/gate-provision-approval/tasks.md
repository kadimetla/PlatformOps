## 1. Routing

- [x] 1.1 `workflows/intake/nodes.py`: `resolve_route`'s routed branch
      sets `approval_required = (intent == Intent.PROVISION)` instead of
      the hardcoded `False`

## 2. Harness

- [x] 2.1 `harness/core.py`'s `_dispatch_provision`: both `ROUTE_RESOLVED`
      payload literals (`unavailable_reason` branch and success branch)
      report `"approval_required": True`

## 3. Schemas / docs

- [x] 3.1 `gateway/schemas.py`: correct `IntakeDecision`'s docstring —
      `approval_required` is no longer inert
- [x] 3.2 `docs/INTAKE_HITL_ROUTING.md`: correct the `## Status` line and
      the `Dispatcher`/`Mutation approval` rows of the Real vs. Designed
      table, dated and noted as a correction

## 4. Tests

- [x] 4.1 `tests/workflows/intake/test_classify_workflow.py`: rename
      `test_provision_resolves_a_route_at_the_intake_graph_level` to
      `test_provision_resolves_a_real_route_gated_by_approval`, add an
      `approval_required is True` assertion; add an `approval_required is
      False` assertion to the `inquiry` unsupported test
- [x] 4.2 `tests/harness/test_core.py`: update the four `approval_required`
      payload assertions affected by provision dispatch;
      `compliance_check`'s stays `False`, unchanged

## 5. Verify

- [x] 5.1 Run the full suite (`uv run pytest`); all pass with no real
      model credentials configured anywhere
- [x] 5.2 `openspec validate gate-provision-approval --strict` passes
