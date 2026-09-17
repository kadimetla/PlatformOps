## 1. Design-record corrections

- [x] 1.1 Update the existing bootstrap, intake-routing, and document-map
      docs with dated, cross-linked terminology corrections; retain the older
      vocabulary as historical context rather than silently rewriting it.
- [x] 1.2 Validate the completed OpenSpec proposal, specs, design, and task
      artifacts with `openspec validate build-org-onboarding --strict`.

## 2. Canonical target and registry contracts

- [ ] 2.1 Add canonical `org/group/team/project/env` target and
      registry-controlled provider-binding Pydantic contracts; no legacy
      persisted `workspace` field.
- [ ] 2.2 Add a deterministic registry loader/resolver with exact-match,
      active-state, and no-fallback behavior.
- [ ] 2.3 Add unit tests for target-key construction, rejected missing/inactive
      entries, ignored client binding values, and binding-digest snapshots.

## 3. Organization onboarding lifecycle

- [ ] 3.1 Define and implement the authenticated applicant entry contract and
      deterministic organization-control proof checks; creating a pending
      record grants no tenant authority and is not a free-text intake path.
- [ ] 3.2 Define an injected read-only cloud-root verifier protocol and a
      scripted fake for tests; do not add a live provider client yet.
- [ ] 3.3 Add deterministic approval/digest and activation transitions so
      only a validated, approved, verified record becomes active.
- [ ] 3.4 Add tests for pending/non-routable records, verification failure,
      insufficient or invalid approval, applicant-to-initial-admin binding,
      and successful activation.

## 4. Provision-flow handoff

- [ ] 4.1 Replace the in-memory known-workspace lookup on the provision entry
      path with a resolved immutable registry context; preserve deny-by-default
      behavior.
- [ ] 4.2 Migrate edge inputs and tests from `workspace` to `env`, with any
      temporary compatibility parsing normalized immediately at the boundary.
- [ ] 4.3 Add an end-to-end fake-adapter test proving that only an active exact
      target binding reaches the provision preflight and that its provider is
      registry resolved.

## 5. AWS verification and operational validation

- [ ] 5.1 Verify the exact AWS Organizations/IAM read-only integration contract
      against current official AWS documentation; record sources and the
      minimum required permission set before writing the adapter.
- [ ] 5.2 Implement the AWS cloud-root verifier with contract tests and no
      account-vending capability.
- [ ] 5.3 Run a narrowly scoped sandbox verification and record evidence;
      do not enable an unverified live adapter by default.

## 6. Final verification and documentation

- [ ] 6.1 Run the focused gateway, onboarding, provision, and harness tests
      without real model credentials.
- [ ] 6.2 Run `openspec validate build-org-onboarding --strict` and update
      status/document-map rows to distinguish the implemented slice from the
      deferred account-vending and project/environment bootstrap work.

## 7. Deferred follow-on: administrator UI

- [ ] 7.1 Create a separate OpenSpec change for an onboarding administrator
      wizard only after the server-side onboarding API, lifecycle, and approval
      contracts are implemented and tested; the wizard must not own provider
      binding, approval, or cloud credentials.
