# Design

## Context

This is a remediation change driven by the independently reproduced findings
in `docs/CONTROL_PLANE_CODE_REVIEW.md`, reviewed against branch commit
`5a9cef3`. The review record remains evidence, not the authoritative design;
this change owns the accepted fixes and their verification.

## Goals / Non-Goals

**Goals:** fail loudly for incomplete durable authentication wiring; avoid
diagnostic secret leakage; restore deterministic authorization/lifecycle
behavior; make tests reproducible; and align documentation with shipped
terminology and behavior.

**Non-Goals:** redesign identity-provider onboarding, introduce live cloud
execution, add customer policy language, or expand principal types beyond the
existing model.

## Decisions

### Treat authentication and secret handling as merge blockers

The registration attempt repository protocol must directly expose every method
used by verification intent and confirmation. Durable and in-memory adapters
must implement the same contract; missing methods are a wiring error, not an
invalid-token result. Diagnostic redaction must remove opaque secret material
regardless of whether it occurs in a URL query, URL path, or arbitrary delivery
exception string.

### Authorization remains explicit and server-derived

Environment scope bindings either match the selected environment or are
rejected at validation. Identity-group membership is resolved only from an
authoritative server-side source. Non-user principals must satisfy an explicit
organization affiliation rule; implicit membership bypasses are prohibited.
Provider attachment/bootstrap review must reject requester self-approval.

### Approval is a lifecycle state, not a preflight impossibility

When governance requires approval, preflight must produce the approval-needed
state necessary to create/seal a plan. The approval path must then re-evaluate
the required conditions. Execution evidence must identify the authorized,
distinct approver; the terminal gate must not mint its own approval proof from
the plan alone.

### Durable and in-memory behavior must agree

Identity-boundary deduplication keys, invitation email canonicalization, and
token protection must agree across implementations. Invitation lookup uses a
keyed HMAC digest, with an explicit migration/compatibility plan if existing
development data needs replacement. Migration paths must leave all fields that
runtime models require populated and non-null.

### Verification must not depend on developer dotenv side effects

Tests must not import a developer `.env` implicitly and change test semantics
or cause network attempts. The canonical full-suite command uses an isolated
environment and no live model/cloud credentials.

## Priorities

**Merge blockers:** H1, H2, M1, M2, M3, M4, M6, M7, L1, L3, L6, L8, and a
reproducible full test suite.

**Required before enabling affected product paths:** M5 (IdP journey), L2
(legacy migration backfill), L4 (execution approver attribution), L5
(execution status cleanup), L7 (strict provider resolution model).

## Migration Plan

1. Add failing regression tests for each merge blocker and fix deterministic
   contracts with no production credentials.
2. Apply/verify migration corrections against fresh and upgrade-shaped
   PostgreSQL fixtures.
3. Run the isolated full suite and strict OpenSpec validation.
4. Re-review the diff; retain the review record and document deferred
   enablement work explicitly.
