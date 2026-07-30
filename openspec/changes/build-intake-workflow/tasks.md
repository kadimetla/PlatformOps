## 1. Gateway schemas

- [x] 1.1 Create `gateway/__init__.py`
- [x] 1.2 `gateway/schemas.py`: `Intent` enum (`provision`, `inquiry`,
      `compliance_check` — exactly these three)
- [x] 1.3 `gateway/schemas.py`: `Scope` (`org`, `bu="root"`, `project:
      str | None`, `workspace: str | None`, `org_bu` property)
- [x] 1.4 `gateway/schemas.py`: `ClarificationQuestion` (`field`,
      `question`, `choices: list[str]`)
- [x] 1.5 `gateway/schemas.py`: `IntakeRequest` (`raw_text`,
      `clarification_round=0` — no identity field)
- [x] 1.6 `gateway/schemas.py`: `IntakeDecision` (`intent`,
      `clarification_questions`, `route=None`, `ready_to_route=False`,
      `evidence`) with a docstring stating `route`/`ready_to_route`
      are inert until the dispatcher change

## 2. Intake workflow

- [x] 2.1 Create `workflows/__init__.py`, `workflows/intake/__init__.py`
- [x] 2.2 `workflows/intake/state.py`: `IntakeState` TypedDict
      (`request: IntakeRequest`, `result: IntakeDecision | None`)
- [x] 2.3 `workflows/intake/tools.py`: Tier 2 prefix table
      (`"provision: "`, `"inquiry: "`, `"compliance_check: "` →
      `Intent`, case-sensitive, exact prefix)
- [x] 2.4 `workflows/intake/tools.py`: `select_intent` bound tool
      (`intent: Intent | None`, `clarifying_question: str | None`)
- [x] 2.5 `workflows/intake/nodes.py`: `classify_workflow` — Tier 2
      check first (no model call on a hit), Tier 3 one bound-tool call
      on a miss, malformed/missing tool call → clarifying question
- [x] 2.6 `workflows/intake/graph.py`: one-node `StateGraph` builder
      (`classify_workflow` → `END`)
- [x] 2.7 `workflows/intake/graph.py`: `intake_request()` entry
      function — builds, compiles, invokes, returns `IntakeDecision`

## 3. Tests

- [x] 3.1 Create `tests/__init__.py`, `tests/workflows/__init__.py`,
      `tests/workflows/intake/__init__.py`
- [x] 3.2 Scripted fake chat model fixture (no real credentials, no
      network call)
- [x] 3.3 Test: Tier 2 prefix match resolves intent, zero model calls
- [x] 3.4 Test: Tier 2 case-sensitivity / non-exact-prefix falls
      through to Tier 3
- [x] 3.5 Test: Tier 3 fake-model tool call resolves a valid intent
- [x] 3.6 Test: Tier 3 fake-model tool call emits a clarifying
      question with `choices` matching the `Intent` enum
- [x] 3.7 Test: malformed/missing tool call never guesses an intent
- [x] 3.8 Test: every output (any tier, any outcome) has
      `route is None` and `ready_to_route is False`

## 4. Verify

- [x] 4.1 Run the new test suite; all tests pass with no real model
      credentials configured anywhere in the environment
- [x] 4.2 `openspec validate build-intake-workflow --strict` passes
- [x] 4.3 Confirm the only existing-file change is `pyproject.toml`'s
      new dependencies (per proposal.md's Impact section) — no other
      existing file modified
