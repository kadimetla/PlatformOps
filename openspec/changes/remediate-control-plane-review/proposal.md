# Proposal

## Why

The control-plane merge-readiness review recorded authentication, secret
handling, authorization, lifecycle, persistence, migration, and documentation
defects in `docs/CONTROL_PLANE_CODE_REVIEW.md`. Several defects would make a
durable login unusable or weaken the deny-by-default boundary. They must be
remediated and independently tested before this foundation branch merges to
`main`.

## What Changes

- Repair durable passwordless confirmation and diagnostic secret redaction.
- Repair authorization, approval, scope-binding, invitation, and principal
  boundary defects identified by the review.
- Align in-memory and PostgreSQL lifecycle semantics and migration behavior.
- Remove unsafe or misleading implementation patterns and correct stale docs.
- Establish a reproducible full-suite verification command isolated from an
  untracked developer `.env`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `passwordless-user-registration`: Durable confirmation and safe diagnostics.
- `organization-membership`: Canonical invitation recipient matching and
  protected invitation token lookup.
- `resource-scope-access-control`: Correct environment matching and principal
  organization boundaries.
- `provision-workflow`: Satisfiable approval guardrails and attributable
  execution evidence.
- `browser-session-auth`: Structurally verified browser session claim use.

## Impact

- Gateway authentication, organization, scope, provider, and provision code.
- PostgreSQL repositories/migrations, tests, developer documentation, and
  verification environment.
- No cloud mutation or provider credential integration is introduced.
