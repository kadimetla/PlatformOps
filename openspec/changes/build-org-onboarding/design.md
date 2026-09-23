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
- Deliver a minimal identity-boundary implementation path with fake-verifier
  tests and no cloud integration or cloud mutation.

**Non-Goals:**

- No self-service sign-up, free-text onboarding, cloud-account vending,
  project/environment bootstrap, or normal resource apply in this change's
  first implementation slice.
- No user-supplied cloud credentials, account IDs, role ARNs, cloud-root
  references, trusted provider selection, Resource Scope bootstrap, or
  Resource Scope access-control implementation.
- No Cloud Provider Service connection, inquiry, attachment, or container
  bootstrap implementation.

## Decisions

### Onboarding is an applicant-initiated control-plane action, not a provision intent

An authenticated organization applicant starts onboarding. They are not
trusted as a tenant administrator merely because they have an email address
or an IdP group. The workflow verifies organization control, records review,
then grants that applicant initial tenant-administrator authority only on
activation. The normal intake and provision paths can only read active
registry rows. This preserves the bootstrap design's disjoint allow-list and
prevents an LLM-classified request from creating future authority.

Organization-control proof for this workflow is control of the configured
identity boundary. The precise customer-facing challenge (for example a domain
DNS challenge or configured IdP-administration proof) is an implementation
decision that must be specified and tested before a production verifier is
enabled. An email-domain match or email-link login alone is explicitly
insufficient.

Cloud-root and provider-boundary verification is deliberately separate. It is
owned by `build-cloud-provider-service`, which may attach provider evidence to
an already active organization but cannot activate, claim, or grant tenant
membership for it. Neither workflow implies the other: an active organization
can have zero provider connections, and a provider connection is unusable
until a later explicit Resource Scope binding exists.

### Resource Scope bootstrap is a separate prerequisite

The applicant identity established by this change is not a target grant and
does not select cloud routing. `build-resource-scope-bootstrap` owns PlatformOps
Resource Scope identity, identity-group access bindings, and registry-controlled
provider resolution. Provisioning consumes an authorized, resolved scope only after
organization activation.

### Admin transport is API/CLI first; onboarding UI is a follow-on change

The first implementation exposes the explicit administrator action through a
structured server-side entry point and CLI/config-review transport.  This
keeps validation, approval, and identity-boundary verification independently
testable before a browser client exists.  A later `build-onboarding-admin-ui`
change may add a web wizard only after this contract is stable; it calls the
same server-side API and never holds cloud credentials, chooses a trusted
provider binding, or makes activation decisions in browser code.  The
existing chat frontend remains out of scope because onboarding is not a
free-text intent.

## Risks / Trade-offs

- [Risk] A registry becomes security-critical configuration → Mitigation:
  `build-resource-scope-bootstrap` owns its deny-by-default lifecycle, review,
  snapshots, and request/model write prohibition.
- [Risk] An applicant could claim an organization they do not control →
  Mitigation: require identity-boundary control proof, bind the approval to
  the applicant issuer-and-subject pair, and grant no tenant authority while
  the record is pending.

## Migration Plan

1. Publish the organization-onboarding correction in the existing architecture
   docs, with a cross-reference to Resource Scope bootstrap.
2. Add admin onboarding validation, fake identity verifier, approval/digest
   handling, and activation tests.
3. Select and verify a production domain/IdP proof mechanism before enabling
   it in any deployment.

## Open Questions

- The durable Resource Scope registry backing store and review mechanism beyond the
  MVP reviewed-file approach are owned by `build-resource-scope-bootstrap`.
- The precise applicant authentication source and customer-domain/IdP control
  challenge are open; they must be selected before the public onboarding entry
  point is implemented.
- Cloud account strategy (`shared`, attached existing container, or
  provider-container bootstrap) is owned by `build-cloud-provider-service`;
  it remains out of scope for this change.
- The exact visual design and launch point for the future administrator wizard
  are deferred until the API contract and approval experience are real.
