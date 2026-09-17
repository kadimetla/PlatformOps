## Context

`docs/BOOTSTRAP_WORKFLOW.md` designs a bootstrap ladder but uses the older
`org:bu:project:workspace` vocabulary and has no implementation.  The real
preflight path currently accepts a `ScopeHint` and looks up in-memory known
workspaces; it does not have a durable registry, provider binding, or
organization lifecycle.  `Actor.user_id` currently receives OIDC `sub` but
the durable requester key must be `issuer + subject`: OpenID Connect specifies
that this pair is the stable unique identifier an RP can rely upon.

## Goals / Non-Goals

**Goals:**

- Define a reviewed onboarding contract that admits an organization before
  any of its targets become routable.
- Make `org:group:team:project:env` the canonical PlatformOps target and
  resolve its cloud provider from trusted registry data.
- Keep requester identity, target ownership, and execution identity separate.
- Deliver a minimal AWS-first implementation path with fake-adapter tests and
  no cloud mutation in its first slice.

**Non-Goals:**

- No self-service sign-up, free-text onboarding, cloud-account vending,
  project/environment bootstrap, or normal resource apply in this change's
  first implementation slice.
- No user-supplied cloud credentials, account IDs, role ARNs, or trusted
  provider selection.
- No multi-cloud adapter implementation before the AWS contract is verified
  against current provider documentation.

## Decisions

### Onboarding is an applicant-initiated control-plane action, not a provision intent

An authenticated organization applicant starts onboarding. They are not
trusted as a tenant administrator merely because they have an email address
or an IdP group. The workflow verifies organization control, records review,
then grants that applicant initial tenant-administrator authority only on
activation. The normal intake and provision paths can only read active
registry rows. This preserves the bootstrap design's disjoint allow-list and
prevents an LLM-classified request from creating future authority.

Organization-control proof has two independent dimensions: control of the
configured identity boundary, and control of the configured cloud-root
boundary. The precise customer-facing challenge (for example domain/IdP
administration proof and an externally configured read-only cloud role) is an
implementation decision that must be specified and tested before a live
adapter is enabled. An email-domain match alone is explicitly insufficient.

### The token identifies the requester; the request selects the target

An authenticated session supplies `issuer + subject` and resolved grants.
The UI/CLI supplies the structured five-segment target.  The gateway validates
the target then performs an exact registry lookup.  A token may carry groups
for authorization resolution, but it is not the source of target binding or
provider selection.  This avoids stale, over-broad token claims and supports
one user working across multiple approved targets.

### Registry-controlled provider bindings

The registry owns `provider`, cloud boundary identifier,
`execution_identity_ref`, optional `provider_workspace`, state, and a version
or digest.  `provider_workspace` is an adapter/tool detail; `env` remains the
platform term.  The registry writes an active/routable target only after its
bootstrap/verification work succeeds.  Exact lookup has no inheritance or
fallback.

### A resolved context is snapshotted before plan and approval

Before planning, deterministic code produces:

```text
ResolvedProvisionContext(
  target=org:group:team:project:env,
  provider_binding=..., registry_digest=...
)
```

The plan and approval digest include the registry digest.  A changed target
binding therefore requires re-resolution and a fresh plan, rather than
redirecting an approved request.

### Minimal first implementation links an existing cloud root

The first AWS slice records and verifies a pre-existing AWS organizational
boundary through an injected verifier.  It does not call account-vending APIs.
This establishes the tenant/security boundary while keeping high-privilege
cloud creation as a later, separately specified bootstrap change.

### Admin transport is API/CLI first; onboarding UI is a follow-on change

The first implementation exposes the explicit administrator action through a
structured server-side entry point and CLI/config-review transport.  This
keeps validation, approval, and cloud-root verification independently
testable before a browser client exists.  A later `build-onboarding-admin-ui`
change may add a web wizard only after this contract is stable; it calls the
same server-side API and never holds cloud credentials, chooses a trusted
provider binding, or makes activation decisions in browser code.  The
existing chat frontend remains out of scope because onboarding is not a
free-text intent.

## Risks / Trade-offs

- [Risk] Renaming the scope vocabulary touches real models and tests →
  Mitigation: a dedicated compatibility migration, one canonical stored `env`
  field, and explicit correction notes; no silent dual schema.
- [Risk] A registry becomes security-critical configuration → Mitigation:
  deny by default, explicit lifecycle state, review/approval, digest snapshots,
  and no request/model write path.
- [Risk] Provider verification details can drift → Mitigation: isolate the
  verifier protocol and verify exact AWS integration semantics against current
  official docs immediately before that task is implemented.
- [Risk] An applicant could claim an organization they do not control →
  Mitigation: require identity-boundary and cloud-root control proof, bind the
  approval to the applicant issuer-and-subject pair, and grant no tenant
  authority while the record is pending.

## Migration Plan

1. Publish the terminology correction in the existing architecture docs.
2. Add target and registry schemas with deterministic unit tests.
3. Add read-only registry loading and exact resolution; keep all records
   non-routable until the onboarding lifecycle exists.
4. Add admin onboarding validation, fake verifier, approval/digest handling,
   and activation tests.
5. Add the AWS verifier only after current-doc research, then run a dedicated
   sandbox verification before enabling it in any deployment.
6. Migrate callers from `workspace` to `env`; accept a documented temporary
   legacy input only at the edge and normalize immediately.

## Open Questions

- The durable registry backing store and review mechanism beyond the MVP
  reviewed-file approach are not selected.
- The precise applicant authentication source and customer-domain/IdP control
  challenge are open; they must be selected before the public onboarding entry
  point is implemented.
- AWS account strategy (`shared`, attached existing account, or per-env
  account vending) is selected per organization/group policy; account vending
  remains out of scope for the first implementation.
- The exact visual design and launch point for the future administrator wizard
  are deferred until the API contract and approval experience are real.
