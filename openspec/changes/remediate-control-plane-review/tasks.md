# Tasks

## 1. Authentication and secret safety — merge blockers

- [ ] 1.1 Add repository protocol methods and durable PostgreSQL implementations
  for verification intent/confirmation; remove silent `getattr` fallbacks and
  verify valid durable magic links confirm exactly once.
- [ ] 1.2 Replace diagnostic secret redaction with a fail-closed approach that
  redacts query-, path-, and free-text-borne magic-link tokens; add regression
  tests.
- [ ] 1.3 Return verified browser-session claims structurally from the first
  JWT verification; remove the signature-disabled second decode and test CSRF
  and logout paths.

## 2. Authorization and approval correctness — merge blockers

- [ ] 2.1 Match environment-targeted scope bindings or reject unsupported
  environment binding targets; add positive and negative tests.
- [ ] 2.2 Make approval-required governance produce a satisfiable approval
  lifecycle and re-evaluate before execution; add plan/approval tests.
- [ ] 2.3 Require distinct requester/reviewer identities for provider
  attachment and bootstrap approval; add denial tests.
- [ ] 2.4 Require explicit organization affiliation for every supported
  principal kind; derive identity-group IDs only from an authoritative
  server-side source and reject caller-asserted group membership.
- [ ] 2.5 Strip chat input before slash-command recognition; verify whitespace
  prefixed protected guest commands receive login guidance and never invoke
  model-backed intake.
- [ ] 2.6 Carry distinct approver identity into sealed approval/evidence and
  remove execution states that cannot occur.

## 3. Durable lifecycle and migration correctness — merge blockers unless deferred enablement

- [ ] 3.1 Align in-memory organization-onboarding dedupe with the PostgreSQL
  identity-boundary uniqueness constraint; add cross-name regression tests.
- [ ] 3.2 Canonicalize invitation emails at command and persistence boundaries
  and convert invitation token digests to keyed HMAC; add compatibility/migration
  handling and recipient-match tests.
- [ ] 3.3 Correct resource-scope migration backfill so upgrade-shaped rows meet
  runtime non-null model requirements; test fresh and upgrade paths.
- [ ] 3.4 Persist/retrieve IdP identity-boundary configuration so the
  post-login IdP journey is reachable; add PostgreSQL integration tests.
- [ ] 3.5 Set `extra="forbid"` on provider resolution contracts and add a
  strict-extra-field regression test.

## 4. Documentation and reproducible verification

- [ ] 4.1 Reconcile `IMPLEMENTATION_STATUS.md` with actual completion state and
  correct remaining `org:group:team:project:env` terminology with a correction
  note.
- [ ] 4.2 Make the full test command isolated from developer `.env` loading;
  verify no test triggers live model/cloud/network behavior.
- [ ] 4.3 Run focused regressions, PostgreSQL tests, isolated `uv run pytest`,
  `openspec validate remediate-control-plane-review --strict`, and a final
  merge-readiness review.
