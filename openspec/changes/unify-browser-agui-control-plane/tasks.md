# Tasks

## 1. Browser-authenticated transport

- [x] 1.1 Add a FastAPI browser-session and CSRF dependency that derives a validated principal; verify missing, expired, cross-origin, and invalid-CSRF runs never start a workflow.
- [ ] 1.2 Replace browser `/runs` local actor-session loading with the validated-principal handoff; verify browser chat no longer depends on a server session file.

## 2. Unified command and A2UI interaction

- [ ] 2.1 Route typed browser control-plane actions through the trusted command router and render safe outcomes as AG-UI/A2UI events; verify authority-bearing payload fields are rejected.
- [ ] 2.2 Add onboarding-review A2UI detail and action surfaces driven only by safe projections; verify no provider, credential, token, or reviewer-identity data is rendered.

## 3. Browser client migration

- [ ] 3.1 Update the React AG-UI client to send same-origin credentials and in-memory CSRF proof; verify no JWT or CSRF proof is persisted in browser storage.
- [ ] 3.2 Remove the browser-facing local-file-session assumption and document HTTP/SSE as the initial unified transport.

## 4. Verification

- [ ] 4.1 Run focused gateway, transport, workflow, and frontend tests with fake sessions and no live model, cloud, or provider credentials.
- [ ] 4.2 Run `openspec validate unify-browser-agui-control-plane --strict`.
