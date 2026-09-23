## 1. Design-record corrections

- [x] 1.1 Update the existing bootstrap, intake-routing, and document-map
      docs with dated, cross-linked terminology corrections; retain the older
      vocabulary as historical context rather than silently rewriting it.
- [x] 1.2 Validate the completed OpenSpec proposal, specs, design, and task
      artifacts with `openspec validate build-org-onboarding --strict`.
- [x] 1.3 Correct the organization-onboarding boundary: identity-boundary
      proof, review, activation, and initial tenant-admin membership belong
      here; cloud-root/provider verification belongs to
      `build-cloud-provider-service`.

## 2. Organization onboarding lifecycle

- [x] 2.1 Define and implement the authenticated applicant entry contract and
      deterministic organization-control proof checks; creating a pending
      record grants no tenant authority and is not a free-text intake path.
- [x] 2.2 Define an injected identity-boundary verifier protocol and a
      scripted fake for tests; do not add DNS, IdP, or other live verifier
      integration yet.
- [x] 2.3 Add deterministic approval/digest and activation transitions so
      only a validated, approved, verified record becomes active.
- [x] 2.4 Add tests for pending/non-routable records, verification failure,
      insufficient or invalid approval, applicant-to-initial-admin binding,
      and successful activation.

## 3. Final verification and documentation

- [x] 3.1 Run the focused gateway, onboarding, provision, and harness tests
      without real model credentials.
- [x] 3.2 Run `openspec validate build-org-onboarding --strict` and update
      status/document-map rows to distinguish the implemented slice from the
      deferred Cloud Provider Service and Resource Scope bootstrap work.

## 4. Deferred follow-on: administrator UI

- [ ] 4.1 Create a separate OpenSpec change for an onboarding administrator
      wizard only after the server-side onboarding API, lifecycle, and approval
      contracts are implemented and tested; the wizard must not own provider
      binding, approval, or cloud credentials.
