## Status
Designed only. No inquiry workflow, executor, or auth code exists on
this branch. Reuses
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s Layer 1/Layer 2
credential machinery, narrowed to read-only, and
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)'s `inquiry` intent as
its entry point. Partly grounded against `design/harness-architecture`'s
real, built `workflows/inquiry/` (`classify_resource_type` →
`existence_check`, two genuinely different operations) — cited as
prior art, not re-verified this session.

## Real vs. Designed
| Area | Status |
|---|---|
| Inquiry workflow (any node) | Not implemented |
| `InquiryRecord` evidence | Designed only |
| Per-tier read-only execution identities (`reader`/`planner`, registry extension below) | Designed only — extends the shared registry's single-`execution_identity` shape |
| `design/harness-architecture`'s `workflows/inquiry/` | Real on that branch, unmerged here; different, narrower scope (existence-check only, no capability-depth model) |

## Core Rule
Inquiry uses grants to decide **how much it may inspect and how
specific its answer can be** — never to mutate anything:

- Answers from public/docs/design knowledge require no cloud access.
- Describing real workspace state requires `describe`+ access on that
  scope.
- Comparing options or proposing changes is bounded by the actor's
  allowed capability, up to `propose_change`.
- Inquiry never executes a mutation, regardless of how high the
  actor's own capability goes elsewhere.

## Three Shapes — Only One Touches the Cloud
```
(a) SCOPED DESCRIBE     "what's running in invoices/prod?"
    -> targets a known project/workspace
    -> full effective_access = min(grant, ceiling) check, same as
       provision's resolve_route
    -> if effective_access >= describe: real cloud read via the
       workspace's READ-ONLY identity (not the provisioner)
    -> else: "not found or not accessible" (see Enumeration
       Protection, below)

(b) SELF ENUMERATION    "what can I access?"
    -> NO cloud call, no registry scan, no provider discovery
    -> pure local read of actor.execution_grants from the session,
       filtered to non-none capability

(c) UNSCOPED ADVISORY   "how should I host a static site?",
                       "compare Terraform and CDK"
    -> NO cloud call — no project/workspace target exists to check a
       grant against
    -> general knowledge only; must not imply knowledge of any
       specific private workspace unless the user names one AND has
       describe access on it
```

## Inspection Depth Scales With Capability
The capability ladder is reused as a dual-purpose vocabulary: a
mutation *ceiling* for provision, an inspection *depth* scale for
inquiry — and the two uses diverge above `propose_change`:

| Effective access | Inquiry may do |
|---|---|
| `none` | Answer generally; cannot inspect or confirm/deny anything about the named private workspace |
| `describe` | Read current stack metadata/state and explain it |
| `plan` | Build/read a non-mutating plan and explain expected changes |
| `propose_change` | Draft change-proposal/PR content — no apply |
| `apply_limited`+ | **Same as `propose_change`** — higher mutation rights buy no deeper inquiry answer; inquiry is capped regardless of what the actor could do in provision |

Example: "what would change if we added CloudFront to invoices/dev?"
— with `plan`+, build a speculative plan and return its summary (no
approval gate, no executor); with only `describe`, explain the change
conceptually without generating an environment-specific plan.

## Credential Matches the Request, Not the Actor's Ceiling
A distinct, important property from provision's design: even an
operator holding `apply_limited` on a workspace should acquire only a
**read-only** credential when the operation being performed is a read.

```
acquired_capability = min(actor's grant, what THIS operation needs)
```

Never "whatever the actor is capable of." Least privilege applied
per-request, not per-actor.

### Registry extension: identity per tier, not one identity per workspace
This requires the shared registry
(`gateway/policy/project_registry.yaml`, described in
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)) to hold more
than one execution identity per workspace — a map keyed by capability
tier, not a single ARN:

```yaml
workspaces:
  prod:
    execution_identities:
      describe: arn:aws:iam::123456789012:role/platformops-invoices-prod-reader
      plan: arn:aws:iam::123456789012:role/platformops-invoices-prod-planner
      apply_limited: arn:aws:iam::123456789012:role/platformops-invoices-prod-provisioner
    max_capability: apply_limited
```

**A real fork was considered and resolved here**: AWS supports
narrowing a single broad identity per-call via an inline session
policy on `sts:AssumeRole`, which would avoid needing separate
identities at all. Rejected in favor of separate per-tier identities,
because the session-policy trick is AWS-specific — Azure RBAC tokens
carry the identity's fixed role assignments with no per-request
narrowing primitive, and GCP impersonation tokens don't offer one
either. Accepting more bootstrap identities is the cost of one
mechanism working uniformly across all three clouds, matching the
reasoning already used for the Azure execution-identity asymmetry in
`EXECUTION_CREDENTIALS.md`. (That doc's registry example, showing one
`execution_identity` per workspace, still stands as the simplest case —
a workspace whose only reachable tier is its ceiling; the map form
applies once a workspace supports multiple inspectable tiers, which
inquiry always requires for anything above `none`.)

## Enumeration Protection
The important security addition. Two cases must produce the **same**
response, so a requester can't probe workspace names to discover which
are real:

```
workspace exists, requester has no describe grant  -> "not found or
workspace does not exist                              not accessible"
```

Never reveal which case occurred. This covers the existence-check
question too ("does invoices-prod exist?") — existence itself requires
`describe`, so there is no separate, weaker tier needed below
`describe` for existence alone. This is the same territory
`design/harness-architecture`'s real `classify_resource_type ->
existence_check` sequence occupies, just with a capability gate this
design's prior art didn't need to model.

The uniform denial applies only to the **specific named target** — the
`none`-tier general/advisory answer (Core Rule, above) can still be
offered underneath it without weakening the denial; the two aren't in
tension.

## Escalation Boundary
Inquiry must never silently escalate from explaining to acting:

```
NOT THIS:  "Here's what would change..." -> [applies the fix]
THIS:      "Here's what would change... I can route this to
           provision as a new request." -> requester explicitly
           initiates a NEW request, back through intake, into the
           full provision graph (plan, approval, executor)
```

Same discipline as everywhere else in this design — no automatic
continuation substitutes for a real gate — applied at the
workflow-boundary level instead of the credential level.

## Inquiry Graph Shape
```
extract_question
  -> resolve_scope                        (may be none — case (c) above)
  -> choose_depth_from_effective_access    (deterministic; the depth
  │                                        table, not an LLM judgment)
  -> maybe_describe_current                (case (a), depth >= describe)
  -> maybe_build_plan                      (case (a), depth >= plan)
  -> answer
  -> record_inquiry_evidence
  -> END
```
No approval gate — nothing here mutates, so there is nothing to
approve. No executor — the read-only credential acquisition happens
inline (Layer 2, narrowed), not through the executor sub-graph, since
there's no plan/approval to bind a digest to.

## Evidence: `InquiryRecord`, a separate schema from `ExecutionRecord`
```python
class InquiryRecord(BaseModel):
    request_id: str
    actor_id: str
    scope: Scope | None
    inquiry_type: Literal["scoped_describe", "self_enumeration", "unscoped_advisory"]
    provider: CloudProvider | None
    read_identity: str | None
    started_at: datetime
    ended_at: datetime
    status: str
```
Deliberately **not** `ExecutionRecord` with `plan_digest`/
`approval_digest` left null. Overloading the execution schema with
nullable approval/mutation fields would blur what's actually a
different kind of event — reads are not executions in the
approval/mutation sense, and the audit model stays clearer with two
narrow schemas than one wide one carrying always-empty fields for an
entire class of records. Persisted independently of checkpoint state,
same rule as `ApprovalRecord`/`ExecutionRecord`.

## How this relates to the existing docs
Entry point is [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)'s
`inquiry` intent. Reuses
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s Layer 1/Layer 2
credential-acquisition mechanics wholesale, narrowed to read-only, and
extends that doc's registry shape from a single `execution_identity`
per workspace to a tier-keyed map (noted here, not silently changed
there — the single-identity example remains valid for its stated
simplest case). Cites `design/harness-architecture`'s real
`workflows/inquiry/` as prior art for the existence-check case, not as
something re-verified this session. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
