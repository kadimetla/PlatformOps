## 1. Design-record corrections

- [x] 1.1 Update the existing bootstrap, intake-routing, and document-map
      docs with dated, cross-linked terminology corrections; retain the older
      vocabulary as historical context rather than silently rewriting it.
- [x] 1.2 Validate the completed OpenSpec proposal, specs, design, and task
      artifacts with `openspec validate build-org-onboarding --strict`.

## 2. Organization onboarding lifecycle

- [ ] 2.1 Define and implement the authenticated applicant entry contract and
      deterministic organization-control proof checks; creating a pending
      record grants no tenant authority and is not a free-text intake path.
- [ ] 2.2 Define an injected read-only cloud-root verifier protocol and a
      scripted fake for tests; do not add a live provider client yet.
- [ ] 2.3 Add deterministic approval/digest and activation transitions so
      only a validated, approved, verified record becomes active.
- [ ] 2.4 Add tests for pending/non-routable records, verification failure,
      insufficient or invalid approval, applicant-to-initial-admin binding,
      and successful activation.

## 3. AWS verification and operational validation

- [ ] 3.1 Verify the exact AWS Organizations/IAM read-only integration contract
      against current official AWS documentation; record sources and the
      minimum required permission set before writing the adapter.
- [ ] 3.2 Implement the AWS cloud-root verifier with contract tests and no
      account-vending capability.
- [ ] 3.3 Run a narrowly scoped sandbox verification and record evidence;
      do not enable an unverified live adapter by default.

## 4. Final verification and documentation

- [ ] 4.1 Run the focused gateway, onboarding, provision, and harness tests
      without real model credentials.
- [ ] 4.2 Run `openspec validate build-org-onboarding --strict` and update
      status/document-map rows to distinguish the implemented slice from the
      deferred account-vending and project/environment bootstrap work.

## 5. Deferred follow-on: administrator UI

- [ ] 5.1 Create a separate OpenSpec change for an onboarding administrator
      wizard only after the server-side onboarding API, lifecycle, and approval
      contracts are implemented and tested; the wizard must not own provider
      binding, approval, or cloud credentials.
