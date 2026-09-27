# Design

## Context

PlatformOps has no self-service user-registration boundary. Existing login and
onboarding material assumes an authenticated applicant, but passwordless
registration must establish only a PlatformOps user identity; it must not turn
a mailbox verification into organization authority. See `proposal.md` and the
two capability specifications for the behavior contract.

## Goals / Non-Goals

**Goals:**

- Create or recover one PlatformOps-controlled user identity after proof of
  mailbox access, without storing a password or raw verification token.
- Make verification consumption resilient to mail-security link scanners while
  preserving bounded, single-use token semantics.
- Provide a deterministic post-login domain-discovery result without using an
  email domain as a membership, cloud-routing, or administrative grant.
- Keep delivery, session issuance, and organization-IdP navigation behind
  narrow interfaces that can be tested with fakes.

**Non-Goals:**

- This change does not create a personal organization, claim a business
  organization, invite a member, provision through SCIM, configure OIDC/SAML,
  or connect to a cloud provider.
- This change does not implement a browser UI or a live email-provider client.
- An email address is not the user primary key, and changing a verified email
  is not part of registration.

## Decisions

### PlatformOps owns the durable user subject

Successful verification creates or recovers a `UserAccount` with a generated
PlatformOps subject and PlatformOps issuer. The verified email is a contact and
display attribute associated with that account, not its primary key. A unique
canonical verified-email lookup prevents duplicate accounts for a returning
person while preserving the stable subject when the contact presentation later
changes.

The rejected alternative is treating an email address, or an external IdP
subject, as the PlatformOps primary key. Email addresses can change and one
person can authenticate through several IdPs; PlatformOps must retain a stable
identity across those events.

### Registration is a deterministic gateway-routed LangGraph workflow

The gateway routes an explicit `/login` command to the login-registration
workflow. The graph uses deterministic Python nodes and conditional edges only:
validate email, create a protected attempt, request delivery, inspect intent,
confirm once, create or recover the user, issue a session, and return a next
journey. No LLM node may decide account existence, token validity, session
issuance, membership, or authorization.

The browser/chat surface is only a workflow launcher. Verification-link GET
and same-origin confirmation POST remain gateway security handlers and call
the same service and PostgreSQL repository as graph nodes. Raw tokens never
enter graph state, checkpoints, events, or logs; safe state holds only IDs and
lifecycle statuses.

### PostgreSQL is the durable store in every deployed environment

PostgreSQL is the authoritative store for user accounts, verified email
contacts, verification attempts, and their audit timestamps in both local
development and production. Local development uses an isolated local
PostgreSQL database; production uses a separately managed PostgreSQL database.
SQLite is not a supported PlatformOps deployment topology.

In-memory registration stores remain unit-test doubles only. PostgreSQL
integration tests exercise migrations, uniqueness constraints, and the
transaction that consumes an attempt while creating or recovering a user. The
application uses a narrow repository boundary so unit tests do not require a
database, but the real server path uses PostgreSQL.

The rejected alternative is SQLite for local development and PostgreSQL only in
production. It creates avoidable behavioral drift around concurrency,
transaction semantics, and schema migrations at the identity security boundary.

### Canonicalize only the email domain for routing and lookup

Registration validates a syntactically acceptable address, preserves the local
part as submitted, and canonicalizes the domain by trimming permitted outer
whitespace, converting the domain to IDNA ASCII where applicable, and applying
ASCII lowercase. It does not remove plus-address tags, rewrite dots, or assume
provider-specific mailbox equivalence. Domain discovery uses this canonical
domain only.

The rejected alternative is provider-specific normalization such as removing
Gmail dots or plus tags. That can merge mailboxes incorrectly and would make
PlatformOps identity behavior provider-dependent.

### Verification attempts persist only protected token material

Each registration request creates a server-generated opaque verification token
with cryptographically secure randomness and a short server-controlled expiry.
The registration store keeps an HMAC digest of the token, user/contact
reference, expiry, consumption timestamp, and attempt identifier; it never
persists the plaintext token. Logs and audit events contain attempt or account
identifiers and redacted email metadata, never the raw token or full link.

Creating a new attempt for the same canonical email invalidates outstanding
unconsumed attempts for that email. Consumption is one atomic state transition:
an unexpired, unconsumed matching digest becomes consumed and cannot issue a
second session or account.

### Verification uses confirmation before consumption

The emailed link opens a verification-intent endpoint that validates the opaque
token without consuming it and presents a confirmation step. A same-origin
POST performs the atomic consumption and session issuance. This reduces the
risk that a mail-security scanner following GET links activates an account.
Both endpoints redact token-bearing URLs from logging, referrers, analytics,
and error output.

The rejected alternative is consuming the token on the first GET request. It
is simpler but makes mailbox protection tools capable of spending a user’s
one-time link before the user reaches it.

### Registration responses are generic and abuse-controlled

The registration initiation endpoint returns the same verification-pending
response for new, existing, malformed-but-acceptable, and rate-limited email
states. Server-side limits apply by canonical email, source/network signal, and
delivery attempt without revealing which limit applied. Delivery failures are
recorded as internal operational evidence but do not disclose account state to
the caller.

The system may avoid sending a duplicate message while a valid attempt exists,
but it preserves the generic response shape. This limits account enumeration
and mail-delivery abuse.

### Active unassociated session is deliberately narrow

On successful consumption, the system issues an authenticated PlatformOps
session for the generated user subject. That session represents an active,
unassociated user and grants no organization membership, tenant administration,
approval, execution, provider routing, or cloud credential. Sensitive later
actions independently authorize the session.

### Domain discovery returns journeys, not grants

Post-login discovery looks up only exact canonical domains verified on active
organizations. It returns a restricted next-journey result: configured
organization IdP/member path for a match, or personal-organization creation and
business-claim request for no match. The result creates no membership and does
not modify a provider binding.

For an organization with a configured IdP, the result directs the member path
to that IdP. The existing authentication boundary validates issuer, audience,
signature, expiry, and subject before resolving any membership; the email-link
session is not substituted for corporate authentication.

## Risks / Trade-offs

- [Risk] A link scanner opens a verification URL → Mitigation: require the
  explicit same-origin confirmation POST before consuming the token.
- [Risk] Email delivery can be delayed or unavailable → Mitigation: bounded
  retries through the delivery abstraction, generic responses, expiry, and a
  fresh-attempt path without exposing account existence.
- [Risk] Email normalization can merge different mailboxes → Mitigation:
  canonicalize the domain only and retain the submitted local part.
- [Risk] A verified business-domain mailbox is mistaken for company authority
  → Mitigation: domain discovery returns a journey only; organization claims,
  membership, and IdP validation remain separate flows.
- [Risk] Token leakage through telemetry or logs → Mitigation: persist only an
  HMAC digest and centrally redact query strings/token fields at every boundary.

## Migration Plan

1. Add the registration and verification contracts behind a server-side
   boundary with fake delivery and fake session implementations.
2. Add PostgreSQL schema migrations and repository operations for users,
   contacts, and verification attempts; retain in-memory stores only for unit
   tests.
3. Direct unauthenticated entry points to registration; retain existing login
   schemas as the downstream authenticated-session boundary.
4. Enable organization-domain discovery only after active verified organization
   domain records exist; unknown domains retain the safe unassociated journeys.
