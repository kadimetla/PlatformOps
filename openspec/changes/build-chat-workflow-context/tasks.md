# Tasks

## 1. Context contracts and deterministic command boundary

- [x] 1.1 Define constrained active-context, workflow-run, and safe summary
  schemas; verify they contain no role, grant, provider, credential, approval,
  or raw workflow-state fields.
- [x] 1.2 Add allow-listed parsing for `/login`, `/context`, `/resume`, and
  `/cancel`; verify unknown slash commands cannot route to a workflow.
- [x] 1.3 Derive guest and authenticated available-context projections from
  live server state; verify guest projections reveal no protected tenant,
  target, provider, or review data.

## 2. Durable context and draft lifecycle

- [ ] 2.1 Persist owner-scoped active and suspended workflow-run metadata in
  PostgreSQL; verify users cannot read, resume, or cancel another principal's
  draft.
- [ ] 2.2 Implement context switch, suspend, resume, and cancel transitions;
  verify completed audit records are retained and protected workflow checks are
  repeated on resume.

## 3. Intake and browser interaction

- [ ] 3.1 Produce constrained candidate intents from ordinary chat input and
  emit A2UI switch confirmation when meaningful active work would be suspended.
- [ ] 3.2 Render a persistent context indicator, context picker, and resumable
  draft list through AG-UI/A2UI; verify browser state is presentation only.
- [ ] 3.3 Render safe header projections for Guest, signed-in user, and
  organization member states; verify roles, grants, targets, provider data,
  tokens, and raw IdP claims are absent.
- [x] 3.4 Add a deterministic guest chat router that permits only public
  login, registration, membership-entry, and help routes; verify a guest
  provision/review request starts no protected workflow or lookup.
- [x] 3.5 Adapt guest-router outcomes to allow-listed AG-UI/A2UI chat surfaces;
  verify the login surface contains no JWT, cookie, CSRF proof, magic-link
  token, organization, target, provider, or authorization data.
- [ ] 3.6 Define a strict public in-chat login-submission command containing
  only email; verify route, organization, target, provider, role, grant,
  credential, token, cookie, and CSRF fields are rejected.
- [ ] 3.7 After `unify-browser-agui-control-plane` browser `/runs` migration,
  route guest `/login` and the login-submit action through the existing
  registration handler; verify no authenticated principal is required for this
  public path and protected paths still require cookie and CSRF validation.
- [ ] 3.8 Connect successful magic-link confirmation to safe browser identity
  and context refresh; verify the JWT remains HttpOnly-only and the CSRF proof
  remains browser-memory-only.
- [ ] 3.9 Connect authenticated provision intake without bypassing session,
  membership, grant, governance, or provider-binding checks.

## 4. Verification

- [ ] 4.1 Add focused gateway, workflow, transport, and frontend tests using
  fake sessions and no live model, cloud, or provider credentials.
- [ ] 4.2 Run `openspec validate build-chat-workflow-context --strict` and
  document the context-versus-authorization boundary.
