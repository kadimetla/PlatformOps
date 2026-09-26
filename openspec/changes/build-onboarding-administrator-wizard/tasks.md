# Tasks

## 1. Safe review API boundary

- [x] 1.1 Define allow-listed pending-request and review-outcome projections; verify raw verification tokens, session tokens, credentials, and provider fields are absent.
- [ ] 1.2 Add authenticated reviewer-only read and review command handlers that delegate to the existing onboarding lifecycle; verify unauthorized, stale, and duplicate requests fail closed.
- [ ] 1.3 Add strict action payload validation; verify provider, binding, account, credential, and browser-derived digest fields are rejected.

## 2. Browser administrator wizard

- [ ] 2.1 Build an authenticated pending-request detail view using only safe API projections; verify the unauthorized state reveals no request data.
- [ ] 2.2 Add explicit approve/reject interaction wired to the review command; verify the resulting lifecycle outcome is rendered without client-side activation logic.

## 3. Verification and boundaries

- [ ] 3.1 Run focused gateway, workflow, and frontend tests without cloud credentials or a live provider.
- [ ] 3.2 Run `openspec validate build-onboarding-administrator-wizard --strict` and record the wizard's provider/credential boundary in developer documentation.
