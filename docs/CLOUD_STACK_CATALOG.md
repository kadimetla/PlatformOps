## Status

Designed 2026-08-16. No Cloud Stack Registry, catalog API, encrypted
artifact store, promotion workflow, full-text index, or semantic index exists.
The closest real code is `workflows/provision/profiles.py`'s in-process
`PROFILE_REGISTRY`, which maps the single `aws-static-web` profile to one
reviewed `TopologySpec`. That is seed data for this design, not an alternate
registry to grow independently.

This document is the canonical contract for reusable provisioning content.
Other workflow documents may consume it, but must not redefine stack
visibility, lookup, promotion, encryption, or version-selection rules.

## Decision

Call the reusable product surface the **Cloud Stack Catalog** and its
authoritative store/API the **Cloud Stack Registry**. Keep content identity,
publication visibility, deployment identity, and the existing provider-plan
contract explicit:

```text
CloudStackDefinition       stable logical identity and discovery metadata
  -> CloudStackRelease     immutable, signed content version
      -> CloudStackPublication
                           scoped visibility + policy certificate + key envelope
          -> CloudStackDeployment
                           target-bound instantiation for one workspace
              -> PlanResult
                           target/state/time-bound provider execution plan
```

`CloudStack` alone is not a schema name. Major IaC systems use "stack" for
different things: AWS CloudFormation and Pulumi use it for a deployed resource
collection/instance, while Terraform Stacks separates reusable configuration
from isolated deployments. PlatformOps therefore always qualifies the term.

Most importantly, the registry reuses a `CloudStackRelease`; it never promotes
or reuses a provider `PlanResult`. A Terraform/OpenTofu saved plan, HCP run, or CCAPI
operation set is bound to a workspace, current-state fingerprint, provider
identity, policy snapshot, and time. Every deployment creates a fresh one.

## Relationship to Existing Provision Contracts

| Existing contract | Cloud Stack meaning |
|---|---|
| `ProfileRegistration` / `ProfileSelection` | Current single-profile lookup; evolves into release discovery/resolution, then may remain as a compatibility adapter |
| `TopologySpec` | Reusable topology payload contained by a release |
| reviewed unit/module templates | Reusable, digest-pinned dependencies of a release |
| `TopologyRevision` | Request-local candidate or successor derived from a release; fluid until sealed |
| `DeploymentPlan` | Canonical target-bound orchestration IR produced after release instantiation |
| `RenderedArtifact` | Target-bound IaC rendered from the deployment plan and reviewed modules |
| `PlanResult` / provider plan | Fresh execution plan for this deployment; never catalog content |
| `SealedPlan` / `ApprovalRequest` | Approval-bound execution object; never reusable across targets |

A release may eliminate repeated topology authoring, structural validation,
module selection, and static certification. It cannot eliminate target binding,
current-state reads, provider planning, policy validation, approval, or
verification.

## Canonical Contracts

The models below are design contracts, not current code.

```python
class CloudProvider(str, Enum):
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"


class PublicationScope(str, Enum):
    GLOBAL = "global"
    SECTOR = "sector"
    ORGANIZATION = "organization"
    ORG_BU = "org_bu"


class ReleaseLifecycle(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class PublicationLifecycle(str, Enum):
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


class PublicationTarget(BaseModel):
    scope: PublicationScope
    sector_id: str | None = None
    organization_id: str | None = None
    business_unit_id: str | None = None


class CloudStackDefinition(BaseModel):
    stack_id: str
    display_name: str
    summary: str
    capabilities: frozenset[str]
    keywords: frozenset[str]
    owner: str


class CloudStackRelease(BaseModel):
    stack_id: str
    version: str
    provider: CloudProvider
    lifecycle: ReleaseLifecycle
    definition_digest: str
    supported_sectors: frozenset[str]
    input_schema_ref: str
    topology_artifact_ref: str
    topology_digest: str
    module_digests: tuple[str, ...]
    static_policy_profile_refs: tuple[str, ...]
    content_digest: str
    author: str
    signature: str


class CloudStackReleaseRef(BaseModel):
    stack_id: str
    version: str
    provider: CloudProvider
    content_digest: str


class CloudStackPublication(BaseModel):
    publication_id: str
    release: CloudStackReleaseRef
    target: PublicationTarget
    lifecycle: PublicationLifecycle
    policy_certification_digests: tuple[str, ...]
    encryption_key_ref: str
    wrapped_dek_ref: str
    publisher: str
    published_at: datetime
    publication_digest: str
    signature: str


class CloudStackPublicationRef(BaseModel):
    publication_id: str
    release: CloudStackReleaseRef
    target: PublicationTarget
    publication_digest: str
    registry_snapshot_digest: str


class CloudStackDeployment(BaseModel):
    deployment_id: str
    publication: CloudStackPublicationRef
    scope: Scope
    provider: CloudProvider
    workspace_snapshot_digest: str
    resolved_inputs_digest: str
    topology_revision_id: str


class ResolvedCloudStackRelease(BaseModel):
    publication: CloudStackPublicationRef
    topology: TopologySpec
    input_schema_digest: str
    verified_module_digests: tuple[str, ...]
    selection_evidence_digest: str
```

Validation rules for `PublicationTarget` are closed, not best-effort:

| Scope | Required | Forbidden |
|---|---|---|
| `global` | no selector | sector, organization, BU |
| `sector` | `sector_id` | organization, BU |
| `organization` | `organization_id` | sector, BU |
| `org_bu` | organization and BU | sector |

A provider-neutral product family may share a logical `stack_id`, but each
provider implementation is a separately validated release variant. A release
never hides provider-specific resources, schemas, or controls in an untyped
generic dictionary. The authoritative release key is therefore
`(stack_id, provider, version)`, never `(stack_id, version)` alone.
One release may have multiple simultaneous publication records, each with a
different destination scope, policy certification, lifecycle, and wrapped DEK;
publication identity is `publication_id`, not part of the release key.

## Registry, Catalog, and Search Index Are Different

```text
Cloud Stack Registry
  authoritative records, ACLs, lifecycle, exact versions, digests,
  signatures, artifact/key references

Cloud Stack Catalog
  authorized, sanitized discovery view derived from registry records

Search index
  rebuildable full-text/vector projection of catalog metadata; never
  authority for existence, access, compatibility, or version selection
```

The registry is the source of truth. An index may be deleted and rebuilt
without losing a release or changing authorization. Search results contain
candidate release references only; every candidate is re-read from the
registry before it may be shown or resolved.

## Lookup Contract

The fixed parent workflow constructs lookup context from authenticated and
registry-resolved values. The user or model never supplies its organization,
BU, sector, provider account, or visibility entitlement.

`sector_id` comes from trusted organization onboarding/governance data, not
from a stack tag or request text. That binding does not exist today and is a
prerequisite for sector publication. Missing or ambiguous classification fails
before catalog lookup; it must never silently fall back to non-sector policy.

```python
class CloudStackLookupContext(BaseModel):
    actor_id: str
    organization_id: str
    business_unit_id: str
    sector_id: str
    provider: CloudProvider
    workspace_id: str
    policy_snapshot_digest: str


class CloudStackCatalogEntry(BaseModel):
    publication_id: str
    stack_id: str
    version: str
    display_name: str
    summary: str
    provider: CloudProvider
    capabilities: tuple[str, ...]
    publication_scope: PublicationScope
    content_digest: str
    publication_digest: str
    required_inputs: tuple[str, ...]
    policy_notes: tuple[str, ...]
    deprecated: bool
```

Only three workflow-facing operations are needed initially:

```python
search_cloud_stacks(
    query: str,
    context: CloudStackLookupContext,
    limit: int = 5,
) -> list[CloudStackCatalogEntry]

get_cloud_stack_requirements(
    publication_id: str,
    context: CloudStackLookupContext,
) -> CloudStackRequirements

resolve_cloud_stack(
    publication_id: str,
    expected_content_digest: str,
    expected_publication_digest: str,
    request: ApplicationProvisionRequest,
    context: CloudStackLookupContext,
) -> ResolvedCloudStackRelease
```

Search is authorization-first:

```text
1. derive trusted actor/org/BU/sector/provider/workspace context
2. query only published, visible, provider-compatible registry rows
3. apply sector and effective-policy compatibility filters
4. perform exact/full-text ranking within that authorized candidate set
5. optionally perform semantic reranking within the same set
6. re-read candidate IDs from the authoritative registry
7. validate required inputs and pin one exact version
8. return a resolved release or an explicit ambiguity/denial
```

Never search all releases and filter afterward: even a title, similarity score,
or missing-result distinction can reveal an unauthorized organization-specific
stack.

## Deterministic Resolution

Semantic similarity answers only "what might fit?" It never answers "may this
actor use it?" or "which version executes?" After authorization and
compatibility filtering, deterministic selection applies:

1. Require a validated, non-revoked release and a `published` publication;
   deprecated release/publication records may be shown only when an existing
   deployment is pinned to them, and either kind of revocation blocks use.
2. Require an exact provider variant and sector compatibility.
3. Require effective-policy compatibility and complete typed inputs.
4. Prefer the most specific permitted publication:
   `org_bu -> organization -> sector -> global`.
5. Honor an organization/workspace version pin before selecting a newer
   compatible version.
6. Never cross a major version or switch provider variants implicitly.
7. If equally valid candidates remain, return a bounded user choice; the model
   does not break the tie.

Selection evidence records the query, candidate release references, rejected
reasons safe to disclose, selected exact version, registry snapshot, and policy
snapshot. This makes a later "why did it choose this stack?" answer auditable.

## Stack Families and Organization Variants

A Cloud Stack is the reviewed implementation of a product outcome, not the
outcome itself. End users may ask for "host my static web app" with little or
no cloud knowledge. They should not have to assemble S3, CloudFront, ACM,
Route53, Kubernetes, Ingress, TLS, bucket policies, or provider-specific
access controls. The catalog maps that product-level intent to one authorized
stack variant for the user's trusted scope.

Use this hierarchy:

```text
application intent
  -> stack family
  -> provider
  -> authorized org/BU/workspace variant
  -> exact versioned topology release
```

For example:

```text
host static web app
  -> static-web
  -> aws
  -> aws-static-web-cdn
  -> v1.0.0
```

`static-web` is a family. It may have multiple reviewed variants because
organizations standardize static hosting differently:

| Variant | Typical resource assembly | When it fits |
|---|---|---|
| `aws-static-web-cdn` | private S3 bucket, CloudFront, OAC, bucket policy, optional ACM certificate and Route53 records | AWS-native CDN-backed static hosting |
| `aws-kubernetes-static-web` | container image, Deployment, Service, Ingress, TLS, DNS | organizations that require all apps to run through Kubernetes |
| `aws-s3-website-basic` | S3 website hosting, bucket policy, optional DNS | simple or legacy cases where the weaker security posture is explicitly allowed |
| `external-cdn-static-web` | artifact bucket plus external CDN/DNS handoff | organizations standardizing on a third-party CDN |

The exact list is allowed to evolve. A global default can seed an initial
implementation, but mature organizations and BUs may publish their own
standard variants once platform and security review decide "this is how our
teams should deploy this capability." Resolution prefers the most specific
permitted publication: workspace policy or pin, then BU, organization, sector,
and finally global default.

Each variant must declare:

- user-facing intent and summary;
- required application inputs, such as app name, source or release reference,
  environment, and optional desired URL;
- generated or registry-derived inputs, such as bucket name, state key,
  namespace, region, DNS zone, provider account, and execution role;
- topology units and dependencies;
- policy constraints, including allowed DNS zones, allowed resource/action
  types, region rules, and approval requirements;
- lifecycle, version, migration notes, and deprecation status.

The model may help discover candidate resource assemblies while humans are
authoring or revising a stack variant. At runtime, the model may explain
choices, classify intent, and gather application-specific facts. It must not
invent the executable resource graph. Planning consumes only reviewed catalog
content, trusted workspace context, and deterministic policy checks.

## Sector and Tenant Policy

A finance stack is not safe merely because its metadata says `finance`.
Effective policy is a deterministic intersection:

```text
effective stack policy =
    global platform policy
  ∩ provider policy
  ∩ sector policy
  ∩ organization policy
  ∩ business-unit policy
  ∩ workspace policy
```

Each lower scope may tighten an inherited constraint; it cannot weaken one.
Examples of finance constraints include approved regions, encryption/key
requirements, public-access denial, mandatory logging and tags, restricted
resource/action types, higher approval quorum, and longer evidence retention.
These are policy data evaluated by deterministic code, not natural-language
instructions evaluated by an LLM.

There are two checks:

- **Publication certification** proves the static release content satisfies the
  policy profiles declared for its intended scopes.
- **Execution validation** recomputes effective policy for the target and checks
  the freshly generated provider plan. Certification never replaces this
  target-time check.

## Immutable Release and Promotion

Content-addressed versions are immutable. Editing topology, schemas, modules,
policy-profile references, discovery metadata that affects selection, or the
provider creates a new release version and digest.

```text
content:       draft -> validated -> deprecated -> revoked
publication:            published -> deprecated -> revoked
                         (org+BU / organization / sector / global target)
```

Publication scopes are not an automatic maturity ladder. A release may have
only an org+BU publication permanently. Broadening visibility creates another
publication and requires authority for the destination scope.

Promotion does not mutate the source release or make an executable plan global.
It creates a signed publication record for the same validated content digest,
with destination-scope policy certification and an encryption envelope usable
by that scope. Global publication requires platform authority; an organization
cannot self-promote its release globally. A release never approves or promotes
itself, including when an offline authoring agent created it.

Minimum promotion gates:

1. canonical schema and topology validation;
2. unit/module provenance and digest verification;
3. provider sandbox render/validate/plan tests;
4. destination sector/policy certification;
5. security review and human promotion approval;
6. immutable content digest and release-author signature;
7. signed destination publication record and audit evidence.

Deprecating either the content release or one publication prevents new
unpinned selection through the affected record but preserves deployment
history. Release revocation blocks every publication; publication revocation
blocks only that visibility grant. Either blocks new planning and resume/apply
through the affected path; impacted deployments must be surfaced for
remediation. Neither operation deletes historical evidence.

## Encryption, Integrity, and Key Scope

Use envelope encryption for release payloads:

```text
topology/schema/module manifest bytes
  -> unique data-encryption key (DEK)
  -> ciphertext in artifact store
  -> one wrapped-DEK record per publication, using that destination's
     KMS key (KEK)
```

Recommended boundaries:

| Artifact | Key boundary |
|---|---|
| global publication | platform registry key |
| sector publication | sector key when isolation requires it; otherwise platform key plus authorization context |
| organization or org+BU publication | organization-scoped key plus registry authorization |
| run-specific rendered artifact/provider plan | workspace/run-scoped key with bounded retention |

Promotion to a broader scope creates a new publication and wraps the existing
content DEK under the destination key boundary; it does not mutate or decrypt
the source publication. If a destination policy requires separate ciphertext,
that copy retains the same verified plaintext content digest. Promotion never
exposes or shares the source organization's key. Key and wrapped-DEK references
are trusted publication fields, not model or request inputs.

Encryption provides confidentiality; it does not establish integrity. Verify
the canonical content digest, module digests, release-author signature, and
publication signature after decryption and before use. Catalog metadata
is a deliberately sanitized projection and may remain searchable; confidential
topology, parameters, organization identifiers, and policy internals are not
embedded into a global semantic index.

Run-specific `plan.bin`, HCP run details, normalized plan JSON, and CCAPI
operation sets follow `PROVISION_WORKFLOW.md`'s sensitive-plan rules. They are
not stored as Cloud Stack releases and use shorter retention than reusable
catalog content.

## Semantic Search: Optional Projection, Not a New Memory Authority

Start without a separate vector database:

```text
Phase 1: structured filters + capability taxonomy + full-text search
Phase 2: embeddings rerank already-authorized candidates
Phase 3: evaluation-backed hybrid ranking if it improves discovery
```

PostgreSQL can hold registry metadata, full-text indexes, and later `pgvector`
if justified. A standalone semantic store is warranted only after catalog size
and retrieval evaluations show a need. Either way, its records contain only
sanitized `CloudStackCatalogEntry` text and
`(publication_id, stack_id, provider, version)` references.

Embedding input may include display name, summary, capabilities, provider,
sector tags safe to reveal, input-field descriptions, resource categories, and
approved example requests. It excludes encrypted topology content, secrets,
tenant-private metadata outside the authorized index partition, policy
internals, state, and execution plans.

An embedding-model change, catalog metadata change, publication change, or
revocation queues reindexing. Registry authorization and version resolution do
not wait for the index: stale or unavailable semantic search falls back to
structured/full-text lookup and can never keep a revoked release executable.

## Provision Flow Integration

```text
ProvisionDraft
  -> build trusted CloudStackLookupContext
  -> resolve authorized CloudStackPublication + exact CloudStackRelease
  -> decrypt + verify release payload
  -> load TopologySpec
  -> create request-local TopologyRevision
  -> bind target inputs into CloudStackDeployment
  -> compile units -> DeploymentPlan -> RenderedArtifact
  -> create fresh provider PlanResult
  -> policy -> seal -> approval -> apply -> verify -> evidence
```

The fixed parent graph owns context, registry authorization, decryption,
signature verification, version pinning, policy checks, sealing, and execution.
An LLM may translate the request into capability/search terms or summarize
authorized candidates. It never receives registry credentials or key access,
cannot widen publication scope, and cannot resolve an arbitrary artifact ref.

The sealed approval/evidence chain adds `stack_id`, exact release version,
release content digest, publication-record digest, and registry snapshot digest.
These are part of artifact provenance covered by `approval_digest`; changing a
release or publication after planning requires a fresh plan and approval.

## Reuse Matrix

| Item | Reusable across deployments? | Registry content? |
|---|---|---|
| definition discovery metadata | Yes | Yes |
| immutable topology/input schemas | Yes | Yes, encrypted payload |
| reviewed unit/module versions | Yes | Referenced by digest |
| static provider/sector certification | Yes, for its exact release and policy versions | Yes |
| target input bindings | No | No; deployment record |
| backend configuration/state fingerprint | No | No; trusted workspace/run context |
| cloud credentials | Never | Never |
| rendered root IaC | No | No; run artifact |
| Terraform/OpenTofu saved plan | No | Never; run artifact only |
| HCP run / CCAPI operation set | No | Never; run reference only |
| approval and execution evidence | No | Evidence store, not catalog |

## Ownership Boundaries

- **Cloud Stack Registry:** release metadata, publication ACLs, lifecycle,
  signatures, artifact/key references, exact-version resolution.
- **Artifact store:** encrypted release payloads and immutable content-addressed
  module bundles.
- **Policy registry:** global/provider/sector/org/BU/workspace constraints; the
  Cloud Stack Registry references policy versions but does not become policy
  authority.
- **Project/workspace registry:** target account/region/toolchain/state owner and
  execution identities; not stack content.
- **Search index:** rebuildable authorized discovery projection.
- **Evidence store:** promotion, selection, approval, execution, verification,
  deprecation, and revocation history.

Do not combine these into a generic registry dictionary. Their writers,
retention, encryption, and authorization rules differ.

## Implementation Order

1. Introduce the contracts and an in-memory adapter backed by the existing
   `PROFILE_REGISTRY`; preserve current `ProfileSelection` behavior. Its test
   publication is explicitly `org_bu=aiq:it` (matching the current dispatcher
   fixture), never implicitly global; production catalog routing remains off
   until trusted sector/publication context exists.
2. Add the trusted organization-to-sector governance binding, then implement
   exact structured lookup, authorization-first filtering, exact
   version pinning, and selection evidence. No semantic dependency.
3. Add immutable artifact storage, envelope encryption, signature verification,
   and release lifecycle operations.
4. Wire `CloudStackRelease -> TopologySpec -> TopologyRevision` into the
   provision parent graph before implementing promotion.
5. Add org+BU/organization publication and the promotion approval/evidence
   path; add sector/global scopes only when their authorities and keys exist.
6. Add full-text discovery and retrieval evaluations.
7. Add semantic reranking only if those evaluations prove material benefit
   without authorization leakage.

The first slice deliberately does not build a generic plugin system, standalone
vector service, cross-cloud universal topology, or automatic promotion engine.

## Acceptance Invariants

- The same release digest is not structurally re-authored for every request.
- No provider execution plan is reused across deployments or promoted.
- Unauthorized releases cannot appear in results, counts, suggestions, or
  semantic candidates.
- Visibility, sector compatibility, policy, lifecycle, and exact version are
  resolved deterministically from trusted context.
- A model cannot choose publication scope, encryption key, artifact reference,
  provider account, or policy override.
- Promotion creates a new signed destination publication only after
  destination-scope approval and certification; it never broadens or mutates
  its source publication.
- Decryption is followed by digest/signature verification before topology load.
- Revocation is authoritative even when a search index is stale.
- Every deployment still produces a fresh current-state-bound provider plan,
  approval, apply credential, and evidence record.

## Sources / Verify Before Build

- AWS CloudFormation defines a stack as a deployed collection of resources:
  https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacks.html
- Pulumi defines a stack as an isolated configured instance of a program:
  https://www.pulumi.com/docs/intro/concepts/stack/
- Terraform Stacks separates reusable component configuration from deployments
  with isolated state:
  https://developer.hashicorp.com/terraform/language/stacks

Before implementation, verify the selected KMS/envelope format, database
row-level authorization behavior, signature algorithm/key rotation, semantic
index metadata filtering, and revocation propagation against the chosen
services. No provider or storage product is selected by this design.
