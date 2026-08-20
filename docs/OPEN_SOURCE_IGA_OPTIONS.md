## Status

Research summary captured 2026-08-19. This is a product/architecture
evaluation note, not an implementation decision. No IGA tool is
integrated in this repo.

The question this document answers is narrow: if an organization wants
a Saviynt-like access request and approval experience without buying
Saviynt, what open-source or open-core tools could PlatformOps leverage
instead of building all of `OPS_IAM_FLOW.md` itself?

## Decision Direction

Use Authentik as the IdP/SSO/group boundary, not as the full access
governance product. If PlatformOps needs a Saviynt-like portal for
request, approval, certification, expiry, revocation, and evidence, the
best fit to evaluate first is an IGA tool such as midPoint or OpenIAM.

Recommended evaluation order:

1. **Evolveum midPoint** for open-source IGA depth and policy-driven
   access-request/approval capability. See
   `MIDPOINT_IGA_DEEP_DIVE.md` for the detailed user-login and
   request-flow fit.
2. **OpenIAM Community Edition** if a fuller IAM/IGA product surface
   with self-service portal and access catalog is preferred.
3. **Apache Syncope** if PlatformOps needs a lower-level identity
   provisioning engine with Apache licensing and is willing to build
   more governance UX around it.
4. **Soffid** as a broader converged IAM/IGA/PAM candidate, pending a
   licensing and integration review.

Do not treat Authentik alone as equivalent to Saviynt. Authentik can
hold users/groups, issue OIDC claims, and participate in SCIM
provisioning. It should not become the ad hoc authority for access
approval policy unless PlatformOps intentionally builds and owns that
governance layer.

## Candidate Comparison

| Tool | Category | Strength | Main concern |
|---|---|---|---|
| Evolveum midPoint | IGA/IDM | Strong open-source IGA: access requests, policy-based approvals, RBAC, certification, audit, connectors | Operational complexity; not an authentication server, so pair with Authentik or another IdP |
| OpenIAM Community Edition | IAM/IGA suite | Self-service portal, access request catalog, workflows, approvals, reviews, SSO/MFA, connectors | Open-core/commercial boundary and licensing/support posture need review |
| Apache Syncope | IDM/provisioning platform | Apache 2.0, REST APIs, admin/end-user UIs, ConnId provisioning connectors, flexible integration surface | More building-block than full Saviynt-like governance experience |
| Soffid | Converged IAM/IGA/IRC/PAM | Broad identity platform positioning, including IGA/PAM-style capabilities | Verify open-source license, supported edition, APIs, and fit before adoption |
| Authentik | IdP/access-management layer | OIDC/device-code login, groups, SCIM, self-hosted IdP fit | Not a full IGA/access-governance workflow engine |

## How This Fits PlatformOps

There are two viable product paths.

Path A: use an external IGA authority.

```text
PlatformOps detects missing access or receives an access request
  -> maps request to governed role/entitlement
  -> creates or links to a request in midPoint/OpenIAM/etc.
  -> IGA tool handles approval, expiry, reviews, evidence
  -> IGA/IdP updates group or entitlement membership
  -> Authentik/OIDC/SCIM/provider propagation completes
  -> PlatformOps login discovery rebuilds ActorSession grants
```

Path B: build PlatformOps's minimal access workflow.

```text
PlatformOps access request
  -> deterministic checks
  -> PlatformOps approval gate
  -> narrow Authentik group membership update
  -> optional SCIM/provider propagation
  -> session refresh
```

Path A is preferable when the organization already wants an enterprise
access-governance system, recurring access reviews, SoD controls,
auditor-facing evidence, and lifecycle management. Path B is acceptable
for an MVP if the needed surface is limited to PlatformOps-specific
roles and the team accepts owning the governance workflow.

In either path, normal provisioning does not grant access. Provisioning
consumes the current `ActorSession` and fails closed when the user lacks
the required grant.

Both paths should use the same PlatformOps backend contract described in
`ACCESS_REQUEST_IMPLEMENTATION_PLAN.md`. That keeps the chat workflow
stable while allowing an org to plug in midPoint, Saviynt, ServiceNow,
Jira, a custom HTTP service, or PlatformOps's internal MVP backend.

## Target Integration Shape

PlatformOps should keep its internal model stable even if the external
IGA tool changes:

```text
AccessRequest
  requester
  target_scope
  requested_role
  requested_capability
  duration
  justification

AccessDecision
  approved | rejected | cancelled | expired
  approver_records
  policy_version
  entitlement_or_group
  external_request_ref

GrantResolution
  execution_grants
  approval_grants
  evidence
```

If midPoint/OpenIAM is integrated, `external_request_ref` points to the
IGA case/request. If PlatformOps runs the MVP workflow itself, it points
to PlatformOps's own access-request record.

## Evaluation Criteria

Before choosing a tool, verify:

- license and production-use terms;
- Docker/Kubernetes deployment shape;
- REST API coverage for creating requests and reading decisions;
- ability to model org/BU/project/workspace entitlements;
- group/role catalog support;
- policy-based approval routing;
- time-bound access and expiry;
- revocation and reconciliation;
- audit export;
- SCIM or connector support for Authentik, LDAP, AWS IAM Identity
  Center, Entra ID, and GCP;
- admin delegation model;
- how easily PlatformOps can map a request to a catalog item without
  letting an LLM choose raw group names.

## Recommended First Experiment

Run a small midPoint spike before building a custom PlatformOps
access-request workflow:

```text
role catalog:
  aiq:it/invoices/dev operator

request:
  user asks for deploy access

approval:
  manager or app owner approves

provisioning result:
  user gets added to the group/entitlement that Authentik or cloud IAM
  can expose back to PlatformOps

PlatformOps result:
  next login sees ExecutionGrant or ApprovalGrant through the normal
  grant-resolution path
```

The test is not "can midPoint do everything?" The test is whether it
can own the access-governance lifecycle cleanly while PlatformOps keeps
its runtime security model: authenticated session, deterministic grants,
policy ceilings, approval for infrastructure mutation, and no direct
LLM authority over access changes.

## Sources

- Evolveum midPoint introduction:
  `https://docs.evolveum.com/midpoint/introduction/`
- Evolveum midPoint approval process:
  `https://docs.evolveum.com/midpoint/features/current/approval-process/`
- Evolveum midPoint current features:
  `https://docs.evolveum.com/midpoint/features/current/`
- OpenIAM request management:
  `https://docs.openiam.com/docs-2026.5.2/end-user-guide-for-selfservice/4-createrequest/`
- OpenIAM product/features:
  `https://www.openiam.com/`
- Apache Syncope architecture:
  `https://syncope.apache.org/architecture`
- Apache Syncope downloads/license:
  `https://syncope.apache.org/downloads`
- Soffid product overview:
  `https://www.soffid.com/`

## How this relates to the existing docs

`OPS_IAM_FLOW.md` defines the internal access-request lifecycle
PlatformOps would need if no external IGA system is used. This document
identifies open-source/open-core products that could own that lifecycle
instead.

`IDP_SELECTION.md` still owns the Authentik choice for IdP/SSO/group
claims. `ACCESS_POLICY_AND_IAM_DISCOVERY.md` still owns login-time
grant discovery. `AUTH_BOUNDARY.md` still owns the rule that workflows
receive an already-authenticated `ActorSession`.
