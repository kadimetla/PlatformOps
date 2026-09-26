## Status
Review record, not a design doc. Covers `feature/create-provisioning-workflow`
at `5a9cef3` against `main` at `8f5ae6d` (174 files, +13051/-6), reviewed
2026-09-26. **No code was changed by this review** — every finding below is
open unless a later entry says otherwise. Each finding was independently
reproduced against the code at the cited `file:line`; none are reported on
model recall alone.

For per-change delivery status see
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) — this document records
defects, not progress, and deliberately does not restate that dashboard.

## What was reviewed

| Subsystem | Entry points | Build state |
|---|---|---|
| Passwordless registration | `gateway/auth/registration.py`, `gateway/auth/postgres.py`, `gateway/auth/domain_discovery.py` | Real; in-memory path verified, durable path not wired |
| Browser sessions | `gateway/browser_sessions.py`, `gateway/browser_sessions_postgres.py`, `transports/browser_auth.py` | Real |
| Organization onboarding | `gateway/organization_onboarding*.py`, `workflows/organization_onboarding/` | Real |
| Organization membership | `gateway/organization_membership*.py`, `workflows/organization_member_onboarding/` | Real |
| Resource Scope | `gateway/resource_scope_{registry,access,governance,bindings,legacy}.py` | Real |
| Cloud Provider Service | `gateway/provider_connections.py` | Real, fake adapters only |
| Provision control plane | `gateway/provision_{plan,execution,handler}.py`, `workflows/provision/{preflight,approval_graph}.py` | Real, fake executor only |
| Chat routing | `gateway/{chat_workflow_context,command_router,guest_chat_router}.py`, `interaction/guest_chat_a2ui.py` | Real |

## Findings

| # | Sev | Finding | Anchor |
|---|---|---|---|
| H1 | High | Magic-link confirmation silently fails against the durable repository | `gateway/auth/registration.py:379` |
| H2 | High | `redact_registration_secret` leaks path-borne tokens into diagnostics | `gateway/auth/registration.py:24` |
| M1 | Med | Environment-targeted role bindings can never match | `gateway/resource_scope_access.py:180` |
| M2 | Med | `require_approval_for_provision` is unsatisfiable | `workflows/provision/preflight.py:84` |
| M3 | Med | In-memory onboarding dedupe key disagrees with the DB unique index | `gateway/organization_onboarding.py:317` |
| M4 | Med | Invitation emails are never canonicalized | `gateway/organization_membership_postgres.py:73` |
| M5 | Med | IdP post-login journey is unreachable in the wired path | `gateway/organization_onboarding_postgres.py:240` |
| M6 | Med | Container attachment and bootstrap permit self-approval | `gateway/provider_connections.py:338` |
| M7 | Med | Non-user principals bypass the organization-membership boundary | `gateway/resource_scope_access.py:148` |
| L1 | Low | Invitation token digest is unkeyed SHA-256 | `gateway/organization_member_onboarding_handler.py:20` |
| L2 | Low | Migration 003 backfill `ALTER` contradicts the column's `NOT NULL` | `gateway/migrations/003_resource_scope_registry.sql:58` |
| L3 | Low | Leading whitespace bypasses the chat command allow-list | `gateway/chat_workflow_context.py:66` |
| L4 | Low | Execution gate cannot verify approver identity | `gateway/provision_execution.py:48` |
| L5 | Low | `ProvisionExecutionStatus.DENIED` is a reserved unreachable value | `gateway/provision_execution.py:16` |
| L6 | Low | `identity_group_ids` is caller-asserted with no provenance | `gateway/resource_scope_access.py:116` |
| L7 | Low | `ProvisioningContainerResolution` omits `extra="forbid"` | `gateway/provider_connections.py:151` |
| L8 | Low | Identity claims are re-decoded with signature verification off | `gateway/browser_sessions.py:328` |

### H1 — Confirmation silently fails against the durable repository
`verification_intent`, `confirm_verification`, and `confirm_and_issue_session`
resolve their store methods by name and fall back to a falsy return:
`getattr(self._attempts, "consume_email_by_digest", None)` →
`if consumer is None: return None`
(`gateway/auth/registration.py:382`, `:390`, `:400`).
`PostgresUserRegistrationRepository` implements neither
`find_active_by_digest` nor `consume_email_by_digest` — it exposes only
`create_or_recover_verified_user`, `save_new_attempt`, `get_attempt`, and
`consume_attempt_create_or_recover_user(attempt_id, token_digest)`, and the
emailed token carries no `attempt_id` (`gateway/auth/postgres.py:46-147`).

Today no production wiring exists: every `attempts=` call site is a test
passing `InMemoryVerificationAttemptStore`. The defect is therefore latent,
not a live outage — but the `getattr` fallback converts a missing-method
programming error into a silent authentication failure. Wire the durable
repository and every `/login` confirmation returns "invalid token" with
nothing logged. Declare both methods on the `Protocol` and call them
directly so an incomplete store fails loudly at wiring time.

### H2 — Secret redaction misses path-borne tokens
`redact_registration_secret` rebuilds the URL after redacting only the
`token` and `verification_token` *query keys*
(`gateway/auth/registration.py:27-32`). When a URL carries its secret in the
path, the query is empty, nothing is redacted, and the function returns the
URL verbatim:

```
redact_registration_secret("https://app.example.com/verify/AbC123")
  -> "https://app.example.com/verify/AbC123"
```

Any other query key (`?code=`, `?t=`) passes through the same way. The sole
call site feeds `str(error)` from the delivery adapter — which has the raw
token in scope — into `record_delivery_failure`
(`gateway/auth/registration.py:362`), so a delivery error embedding a
path-style magic link writes a live verification token to diagnostics. The
existing test only covers the `?token=` form
(`tests/gateway/auth/test_registration.py:264`), which is why this survived.

### M1 — Environment-targeted role bindings can never match
`ScopeBindingTargetKind.ENVIRONMENT` is an accepted, validated
`ScopeBindingTarget.kind`, but the `ancestor_ids` map in `_target_matches`
covers only ORGANIZATION, BUSINESS_UNIT, TEAM, and PROJECT
(`gateway/resource_scope_access.py:180-186`). An ENVIRONMENT-targeted binding
falls through to `ancestor_ids.get(target.kind) == target.resource_id` →
`None == "env-…"` → `False`. The grant is silently ignored.

The omission is asymmetric: the *same* enum is used by the guardrail store,
where ENVIRONMENT is first-class
(`gateway/resource_scope_governance.py:36`). Fail-closed, so not an
escalation — but whoever builds the binding administration UI gets a target
kind that validates and then never works. Either wire it or reject it in
`_validate_inheritance` the way SCOPE + inherit is rejected
(`gateway/resource_scope_access.py:81-85`).

### M2 — `require_approval_for_provision` is unsatisfiable
Preflight hardcodes `approval_present=False`
(`workflows/provision/preflight.py:84`), and nothing re-runs
`ResourceScopeGovernanceEvaluator` after the approval graph. A scope covered
by a policy with `require_approval_for_provision=True` is therefore `DENIED`
at preflight, before a plan can be sealed — the approval graph that would
satisfy the guardrail sits downstream of the gate blocking it
(`gateway/resource_scope_governance.py:70-75`). `approval_present=True` is
never passed anywhere in the repo, including tests, so the path is entirely
unexercised.

### M3 — In-memory dedupe disagrees with the DB constraint
`save_pending` keys duplicates on
`(organization_name.casefold(), boundary.kind, boundary.reference.casefold())`
(`gateway/organization_onboarding.py:317-322`), while the production unique
index is `(boundary_kind, lower(boundary_reference))` only
(`gateway/migrations/001_organization_onboarding.sql:33-34`). Two requests
claiming `acme.com` as "Acme" and "Acme Inc" both succeed in memory —
contradicting the raised message "already exists for this identity
boundary" — and the second fails in Postgres. The existing test re-submits an
identical name, so it does not cross the divergence.

### M4 — Invitation emails are never canonicalized
`OrganizationInvitation.canonical_email` is a plain `str` with no
normalization, and neither `create_invitation` nor `accept_invitation` calls
`canonicalize_email`; `canonicalize_email` does not appear in the module at
all. The recipient check compares the stored value byte-for-byte against
`auth_verified_email_contacts.canonical_email`, which *is* canonicalized
(`gateway/organization_membership_postgres.py:73`, `:107-108`, `:160-161`).
An invitation created for `alice@Example.COM` never matches the stored
`alice@example.com`, and the recipient gets
`OrganizationInvitationRecipientMismatch` permanently.

### M5 — IdP post-login journey is unreachable
`find_active_domain` constructs `ActiveOrganizationDomain` without `idp`, and
`gateway/organization_onboarding_postgres.py` never references `idp` at all
(`:240`). Migration 001 constrains `boundary_kind IN ('domain','idp')` but
stores no column naming *which* IdP
(`gateway/migrations/001_organization_onboarding.sql:30`, `:43`, `:63`).
`PostLoginDomainDiscoveryService.discover` therefore never takes its
`match.idp is not None` branch: a user at an IdP-configured organization is
routed to `ORGANIZATION_MEMBER_ONBOARDING` instead of
`ORGANIZATION_IDP_AUTHENTICATION`. Only test fakes exercise the branch.

### M6 — Attachment and bootstrap approvals permit self-approval
`approve_attachment` checks `may_review_container_attachment` but never
compares `actor_id` against `request.requested_by`; `approve_bootstrap` is
the same (`gateway/provider_connections.py:338`/`:366`, `:423`/`:447`). One
actor holding both permissions can request and then approve a container
attachment, or a provider-container creation, in two calls. The provision
path explicitly forbids exactly this
(`workflows/provision/approval_graph.py:47-48`), so this is an inconsistency
between two boundaries the design treats as equivalently "reviewed".

### M7 — Non-user principals bypass the membership boundary
`_has_active_membership` returns `True` for every principal whose kind is not
USER (`gateway/resource_scope_access.py:148-153`). Identity-group and service
principals are therefore never checked against
`ActiveOrganizationMembershipLookup`, so the organization boundary is
enforced for humans only. Registry-controlled bindings still gate the grant,
but the cross-organization guard that applies to users does not apply here.
If that is intended, the reasoning belongs in the docstring; if not, services
need their own organization check.

### L1 — Invitation token digest is unkeyed
`_invitation_token_digest` is bare `sha256(token)`
(`gateway/organization_member_onboarding_handler.py:20-22`), while every
other secret digest on this branch is HMAC-keyed (`digest_verification_token`,
`digest_csrf_proof` at `gateway/browser_sessions.py:36-42`).
`organization_invitations.token_digest` is the sole lookup key, so a read of
that table yields an offline-verifiable oracle against guessed tokens with no
server-side secret required.

### L2 — Migration 003 backfill contradicts its own `NOT NULL`
`CREATE TABLE` declares `organization_slug TEXT NOT NULL`
(`gateway/migrations/003_resource_scope_registry.sql:44`), but the backfill
path adds it nullable with no default and no populate step
(`:58`). On a database where `resource_scopes` predates the column, existing
rows get `NULL` and `resolve_active` builds `Organization(slug=None)` →
`ValidationError` instead of returning the scope.

### L3 — Whitespace bypasses the command allow-list
`parse_chat_command` tests `text.startswith("/")` *before* stripping
(`gateway/chat_workflow_context.py:66`), while `_is_protected_command` strips
first (`gateway/guest_chat_router.py:111`). `" /provision"` therefore parses
as `None` — ordinary natural language — rather than `UNKNOWN`. Because the
guest router's protection is gated on `command.kind is UNKNOWN`
(`gateway/guest_chat_router.py:95`), the `LOGIN_REQUIRED` branch is never
reached and the text goes to model-backed intake. Strip first, then test the
prefix.

### L4 — Execution gate cannot verify approver identity
`ProvisionExecutionGate.execute` accepts any `ProvisionApprovalDigest` that
digest-matches the plan (`gateway/provision_execution.py:53`), and
`ProvisionApprovalDigest.for_plan(plan)` mints one from the plan alone
(`gateway/provision_plan.py:76-77`). The digest chain proves *this approval
belongs to this plan*, never *a distinct authorized human approved it*. The
real separation exists only in the approval graph
(`workflows/provision/approval_graph.py:47-60`), so the terminal gate cannot
detect a caller that skipped it. `ProvisionExecutionEvidence` also records no
approver (`gateway/provision_execution.py:19-29`), so the audit trail cannot
answer "who approved this". Carry approver identity into the approval record
before a live executor is wired.

### L5 — Reserved unreachable enum value
`ProvisionExecutionStatus.DENIED` (`gateway/provision_execution.py:16`) is
never constructed — the gate raises on every denial. This is the pattern the
codebase explicitly rejects elsewhere: "no reserved, unreachable values"
(`gateway/schemas.py:20-22`). M1 is the same class of defect.

### L6 — `identity_group_ids` is caller-asserted
`ResourceScopeAuthorizationRequest.identity_group_ids` is supplied by the
caller and matched directly against identity-group bindings
(`gateway/resource_scope_access.py:116`, `:166-172`). No production caller
populates it yet — only a test — so this is latent. When it is wired, the
value must be derived from the authoritative membership store, never from the
request body or a token claim; this repo already removed one attempt to read
groups from a token (`aca4fe3`).

### L7 — Missing `extra="forbid"`
`ProvisioningContainerResolution` is the only model in
`gateway/provider_connections.py` without
`model_config = ConfigDict(extra="forbid")` (`:151-155`).

### L8 — Unverified re-decode of identity claims
`_decode_identity_claims` re-parses the token with
`options={"verify_signature": False}` (`gateway/browser_sessions.py:328-330`)
to recover `sid` for the CSRF and logout paths. It is safe today because
`authenticate()` verified the same token string first, and `sid` was already
available from that verified decode — but the guarantee is positional, not
structural. Returning `sid` from `authenticate()` removes the second parse.

## Test-suite state

`uv run pytest` → **310 passed, 16 skipped, 2 failed** (3.3s).

Both failures are pre-existing on `main` and are **not** caused by this
branch:

- `tests/transports/test_cli.py::test_login_requires_issuer`
- `tests/transports/test_cli.py::test_login_requires_client_id`

Cause: importing `litellm` calls `load_dotenv()`, which loads the repo's
untracked `.env` into `os.environ`. `tests/transports/test_http.py` imports
the HTTP transport, so once it runs, `PLATFORMOPS_OIDC_ISSUER` and
`PLATFORMOPS_OIDC_CLIENT_ID` are set for the rest of the session. The CLI
parser reads those as argparse defaults
(`transports/cli.py:81-82`), so the "requires X" tests stop seeing a missing
argument and attempt a real network call. Both files are untouched by this
branch; the tests pass in isolation and fail after `test_http.py`. Reproduce
with `uv run pytest tests/transports/test_http.py tests/transports/test_cli.py`.

Side effect worth noting independently: any process importing `litellm` from
this working directory inherits the developer's `.env`, including
`OPENAI_API_KEY`.

## Documentation accuracy

Two doc defects found while grounding the review:

- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) contradicts itself.**
  "Explicitly not built yet" lists "Organization memberships, invitations…"
  and "Provision approval, execution, evidence" (`:86-89`), while the Change
  status table in the same document says membership records and `/join-org`
  are implemented (`:51`) and that sealed plan approval, reviewer separation,
  and execution evidence are implemented (`:54`). "Recommended next review
  sequence" (`:71-82`) likewise describes work the table marks done. As the
  stated cross-change navigation dashboard, it should not disagree with
  itself.
- **The `org:group:…` correction landed only partly.**
  `docs/BOOTSTRAP_WORKFLOW.md` now uses `org:bu:team:project:env`, but
  `docs/INTAKE_HITL_ROUTING.md:18` and the map row in
  `docs/HARNESS_DESIGN.md:12` still assert
  `org:group:team:project:env` as canonical — the vocabulary
  `build-resource-scope-bootstrap` explicitly replaced, reserving `group`
  for identity groups. Per `CLAUDE.md`'s "correct prior docs in place, with a
  note", both need the same `corrected by build-resource-scope-bootstrap`
  annotation `BOOTSTRAP_WORKFLOW.md` received.

## How this relates to the existing docs

- Extends [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md): that note
  tracks *what is built* per OpenSpec change; this one records *what is
  defective* in the built code. Neither restates the other, and OpenSpec
  `tasks.md` files remain the authoritative completion ledger.
- Findings M1, M2, L4, L5, and L6 concern behavior specified by
  [`build-resource-scope-bootstrap`](../openspec/changes/build-resource-scope-bootstrap/)
  and [`build-provision-flow`](../openspec/changes/build-provision-flow/);
  those changes' specs remain authoritative for intended behavior, and
  nothing here amends them.
- H1, H2, and M4–M5 concern
  [`build-user-registration`](../openspec/changes/build-user-registration/)
  and
  [`build-organization-member-onboarding`](../openspec/changes/build-organization-member-onboarding/).
- The documentation defects above apply to
  [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) and
  [HARNESS_DESIGN.md](HARNESS_DESIGN.md); neither was edited by this review.
