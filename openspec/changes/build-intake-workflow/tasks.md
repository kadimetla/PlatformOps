## 1. State and models

- [x] 1.1 Create `workflows/intake/__init__.py`. **Done.**
- [x] 1.2 Create `workflows/intake/state.py`: `IntakeRequest`,
      `IntakeResult`, `IntakeState`. **Done.**

## 2. Classification

- [x] 2.1 Add a `select_workflow` bound tool. **Done** — prompt-based
      enforcement, matching `select_resource_type`'s convention.
- [x] 2.2 Implement `classify_workflow` node. **Done** — Tier 2 prefix
      check (`"drafting:"`/`"inquiry:"`, exact-match, case-sensitive)
      first, Tier 3 `select_workflow` model call only if no prefix
      matched.
- [x] 2.3 Handle a Tier 3 response with no usable tool call or an
      out-of-candidate value as a clarifying-question case. **Done.**

## 3. Graph and entry function

- [x] 3.1 Create `workflows/intake/graph.py`: `build_intake_graph()`,
      one node, no router. **Done.**
- [x] 3.2 Create `workflows/intake/intake_request.py`:
      `intake_request(request: IntakeRequest) -> IntakeResult`.
      **Done.**

## 4. Tests

- [x] 4.1 Write `tests/test_workflows_intake.py`. **Done**, 5 tests.
- [x] 4.2 Cover: `"drafting:"` prefix, no model call. **Done.**
- [x] 4.3 Cover: `"inquiry:"` prefix, no model call. **Done.**
- [x] 4.4 Cover: unprefixed text resolves via Tier 3. **Done.**
- [x] 4.5 Cover: unresolvable text returns a `clarifying_question`.
      **Done.**
- [x] 4.6 Cover: out-of-candidate-set model response treated as
      unresolved. **Done.**

## 5. Verification

- [x] 5.1 Run `uv run python -m pytest tests/ -q`. **Done** — 66 passed
      (61 pre-existing + 5 new), no regressions.
- [x] 5.2 Run `openspec validate build-intake-workflow --type change`.
      **Done** — see below.
