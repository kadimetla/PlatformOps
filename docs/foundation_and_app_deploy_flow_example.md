# Foundation Setup → App Deploy: A Worked Example

## Status
Synthesis, not a build log — same role as
`docs/end_to_end_flow_example.md`, but for the foundation/app-layer path
instead of the static-hosting path that doc already traces. Ties
together `docs/foundation_app_layering_and_iam_tiers.md`,
`docs/eks_helm_mcp_integration.md`,
`docs/infra_discovery_and_platform_app_split.md`, and
`docs/foundation_discovery_and_capability_matching.md` into one ordered
walkthrough. Introduces no new decisions — see those docs for the
reasoning behind each step. **Note**: this walkthrough exercises only
the "nothing found" and "reuse an already-recorded foundation" branches
— the unmanaged-foundation adoption-review branch isn't dramatized here,
see the capability-matching doc's Part D for that case on its own.

## The example
Same Acme Payments BU as `docs/end_to_end_flow_example.md`'s Alice
scenario — this is what has to happen *before* an app-layer request like
hers can succeed against real compute infra, not a different BU.

**Bob** (`channel_user_id="bob@acme.com"`,
`TeamMember(role="admin", scope="foundation")`) sets up the foundation.
**Alice** (`channel_user_id="alice@acme.com"`,
`TeamMember(role="requester", scope="app")`) deploys onto it afterward.

## Phase 1: Bob sets up the foundation

1. Bob requests: *"Set up a VPC and EKS cluster for the Payments team's
   new service."*
2. Gateway resolves org/BU/session as usual. **New check**: `TeamMember`
   lookup confirms Bob's `scope` includes `"foundation"`
   (`docs/infra_discovery_and_platform_app_split.md` Part C) — a
   requester with `scope="app"` only would be denied here, before even
   reaching skill resolution. This is a structural boundary, not a
   policy an agent has to remember to check.
3. `resolve_skill()` matches `provision-foundation` — the new bundled
   skill from `docs/foundation_app_layering_and_iam_tiers.md` Part A.
4. **Discovery before creation, not blind provisioning**: the agent
   checks whether a foundation already exists for this BU — any
   existing `FoundationRecord`, cross-checked against a live
   `ccapi-mcp-server list_resources`/Resource Explorer query
   (`docs/infra_discovery_and_platform_app_split.md` Part A). This is
   actually a three-way branch, not a yes/no check — see
   `docs/foundation_discovery_and_capability_matching.md` Part A for
   the other two outcomes this walkthrough doesn't exercise: an
   existing, already-recorded foundation (reuse it, load its
   `discovered_capabilities`, skip straight to Alice's phase) or an
   *unmanaged* foundation found live with no `FoundationRecord`
   (requires an adoption review at the same approval bar as creating
   one, Part D of that doc). For Bob specifically: none found either
   way — proceeds to draft.
5. Draft via `awslabs.eks-mcp-server`'s `manage_eks_stacks`
   (`--allow-write`): the VPC, the EKS cluster service role, and a
   **separate** node IAM role — never reused across the two, per the
   four-role correction in
   `docs/infra_discovery_and_platform_app_split.md` Part B. Each
   `iam:PassRole` grant involved is scoped to exactly these two role
   ARNs, never `Resource: "*"`.
6. Vibe Diff produced. Foundation-tier resource types are **always**
   human-approval (`docs/foundation_app_layering_and_iam_tiers.md`
   Part A's tier rule) — routes straight to Bob regardless of any
   autonomous-approval threshold that would apply at app tier.
7. Bob approves. `ApprovalRecord` created; on execution, a
   `FoundationRecord` is written:
   `{foundation_id, org_id="acme", bu_id="payments", resource_type="AWS::EKS::Cluster", approved_plan_id, status="active"}`.
8. Audit log captures the chain, tagged with `scope="foundation"` — not
   just "someone at Acme Payments did something," which was all the
   audit log distinguished before this design.

## Phase 2: Alice deploys an app onto it

9. Alice requests: *"Deploy the payment-processing service to our EKS
   cluster."*
10. `TeamMember` scope check: Alice's `scope="app"` is sufficient — this
    is an app-layer request, so it passes without needing
    `scope="foundation"`. Same check as step 2, opposite outcome,
    because it's checking against a different request's tier.
11. `resolve_skill()` matches `deploy-to-k8s` (named `deploy-to-eks`
    until `docs/multi_cloud_foundation_and_iam.md` confirmed it isn't
    AWS-specific) — the new bundled skill from
    `docs/foundation_app_layering_and_iam_tiers.md` Part C.
11a. **New step 0 of `deploy-to-k8s`**: load the found
    `FoundationRecord`'s `discovered_capabilities` — K8s version,
    installed add-ons, available ingress/storage classes, the workload-
    identity target Alice's new app identity must bind to — and select
    chart values compatible with them, rejecting or flagging anything
    the foundation can't actually satisfy
    (`docs/foundation_discovery_and_capability_matching.md` Part C/E).
12. **Dependency check**: the skill's procedure requires an active
    foundation. The Gateway looks up `FoundationRecord` for
    `bu_id="payments"` — finds the one Bob created in Phase 1,
    `status="active"`.
13. Execution backend: `containers/kubernetes-mcp-server`'s
    `helm_install`, targeting the namespace allow-listed for Payments,
    using a kubeconfig scoped to **only** this BU's cluster context —
    per `docs/eks_helm_mcp_integration.md`'s cross-BU kubeconfig risk
    finding, never a shared multi-BU kubeconfig.
14. The workload's IAM: a new IRSA role scoped to just the specific
    resources this service needs (e.g., one DynamoDB table), with a
    permissions boundary attached — distinct from both the cluster role
    and the node role Bob's phase created.
15. Vibe Diff (a `helm diff`/dry-run output here, not a CFN/Terraform
    plan) goes to `security_agent`. App-tier risk rules apply — this can
    be autonomously approved if it matches a low-risk, allow-listed
    pattern, unlike Phase 1's mandatory human gate.
16. `BrokeredToolDispatcher.evaluate_intent()` — same deny-by-default
    shape as today, **plus** the new `depends_on_foundation_id` check
    from `docs/foundation_app_layering_and_iam_tiers.md` Part D:
    re-confirms the `FoundationRecord` from step 12 is still
    `status="active"` **at dispatch time**, not just at plan time — a
    foundation could be decommissioned in the gap between planning and
    dispatch, and this check is what catches that.
17. `helm upgrade --install` executes. Result streams back to Alice.
18. Audit log records both `scope="app"` and the `foundation_id` this
    deploy depended on — so a future foundation decommission can be
    checked against every dependent app deploy deliberately, not
    discovered by outage.

## What's real vs. design today
| Step | Status |
|---|---|
| 1–2 (request, `TeamMember.scope` check) | Design only — `TeamMember`/`scope` don't exist in `gateway/schemas.py` |
| 3, 11 (skill resolution) | Design only — no `resolve_skill()`, no bundled-tier loading either (`docs/skill_loading_and_enforcement_gap.md`) |
| 4 (discovery-before-creation, drift check) | Design only |
| 5 (`manage_eks_stacks`) | Real, maintained MCP server exists; not integrated into this project's `mcp_server/external_servers.py` yet |
| 6–8 (foundation approval, `FoundationRecord`, audit) | Design only |
| 12 (dependency check) | Design only |
| 13 (`helm_install` via `kubernetes-mcp-server`) | Real, maintained MCP server exists; not integrated yet |
| 14 (IRSA + permissions boundary) | Design only |
| 15–16 (review, dispatcher gate incl. foundation re-check) | Dispatcher's core shape is real and tested (`gateway/tool_dispatcher.py`); the foundation-dependency check is new design, not built |
| 17–18 (execution, audit) | Audit table exists and is tested; `scope`/`foundation_id` fields are new, not built |

Nothing in this phase-1/phase-2 flow is built. Every piece it exercises
was itself design-only in the doc it came from — this is where they all
have to fit together, not a claim that any of it works today.

## How this relates to the existing docs
- Parallel document to `docs/end_to_end_flow_example.md`, same
  synthesis role, for the foundation/app path instead of the static-
  hosting path.
- Exercises `docs/foundation_app_layering_and_iam_tiers.md`'s
  `provision-foundation`/`deploy-to-k8s` skills and `FoundationRecord`,
  `docs/eks_helm_mcp_integration.md`'s two-MCP-server split and
  kubeconfig-scoping rule, and
  `docs/infra_discovery_and_platform_app_split.md`'s discovery-before-
  creation step, four-role IAM correction, and `TeamMember.scope`
  dimension — all in one ordered path.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  same relationship every doc in this set has to it.
