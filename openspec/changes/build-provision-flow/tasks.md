# Tasks

## 1. Gateway and authenticated handoff

- [ ] 1.1 Define `/provision` route and validate session before graph startup.
- [ ] 1.2 Pass only safe principal reference and `scope_id`; test exclusion of
      tokens, credentials, and client provider hints.

## 2. Resolved control-plane context

- [ ] 2.1 Integrate active-membership lookup; deny missing or revoked membership.
- [ ] 2.2 Integrate scope authorization, guardrails, and exactly-one binding;
      return setup-required for absent or ambiguous prerequisites.
- [ ] 2.3 Seal context IDs/versions and require a fresh run on drift.

## 3. Plan, approval, execution, evidence

- [ ] 3.1 Preserve and test current non-mutating typed preflight.
- [ ] 3.2 Add deterministic plan/policy sealing and approval-digest checks.
- [ ] 3.3 Add checkpointed HITL approval with requester/approver separation.
- [ ] 3.4 Add separately authorized execution and terminal evidence after gates.

## 4. Verification

- [ ] 4.1 Run focused tests without cloud credentials or live provider.
- [ ] 4.2 Run `openspec validate build-provision-flow --strict`.
