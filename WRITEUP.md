<!--
Kaggle Writeup draft — Track: Agents for Business
Word count target: ~2,250 words (cap is 2,500). Word count is approximate;
recount before submitting. Bracketed [ ] notes are placeholders for you to
fill in with real screenshots/numbers/links once the demo is run — do not
submit with placeholders still in place.
-->

# PlatformOps Agent
### From spec to compliant, provisioned AWS infrastructure — with a human-reviewable approval gate at every step

**Track: Agents for Business**

---

## The Problem

Every organization running workloads on AWS depends on a platform engineering
or ops team to turn application requirements into provisioned, secure,
compliant infrastructure. In practice that means tickets, manual reviews, and
a compliance process that lags behind what's actually been deployed. Small
and mid-sized teams without a dedicated platform org feel this hardest: they
either under-invest in infra hygiene or burn engineering time that should go
to product work.

We wanted to build the thing platform ops teams actually do — parse a
requirement or architecture spec, check it against internal standards,
provision the approved infrastructure, and require a real sign-off before
anything touches production — as an agentic system, and make every one of
those steps auditable rather than a black box.

## Why Agents

This isn't a scripting problem. Deciding whether a spec is compliant, whether
a provisioning plan is safe to execute, and how to react when it isn't,
all require judgment applied to unstructured input (a request, a spec, a
diagram) — not a fixed pipeline. Agents let us encode *procedure* (what to
check, in what order, and what "acceptable" means) separately from *reach*
(the actual ability to call AWS), so the same review procedure can be
audited, versioned, and reused independently of what infrastructure it's
being applied to.

Critically, we wanted agentic judgment on the read/reasoning side, and a
narrow, deterministic, non-agentic layer on the side that actually touches
real cloud resources — the architecture below is built around that split.

## Solution & Architecture

Given a structured infrastructure spec (in this MVP: a YAML description of
the desired resources — see `spec/example_submission.yaml` — with diagram
image upload as a documented next step, not built here), the system:

1. **Checks compliance** against a versioned reference architecture
   (`spec/reference_architecture.md`), written as Given/When/Then scenarios —
   e.g. "no S3 bucket may have public write access," "CloudFront must force
   HTTPS," "resources must stay within the approved region and cost
   ceiling." This check runs deterministically via `spec/check_compliance.py`
   — no model call needed, so results are reproducible and auditable, not
   just "the LLM said it was fine."
2. **Drafts a provisioning plan**, if compliant, via a **Provisioning
   Agent** for the user's chosen toolchain, which produces a plain-English
   summary of exactly what it's about to do — resources, region, estimated
   monthly cost — before touching anything.
3. **Requires explicit approval** from a separate **Security Agent**, which
   checks the plan using its own `security-review-checklist` procedure
   before anything is allowed to execute.
4. **Provisions the resources** by routing to existing, officially
   maintained MCP servers rather than hand-rolled cloud code — see below.

```
User request / spec
        │
        ▼
platformops_orchestrator (ADK root agent)
        │
        ├── sdlc-diagram-compliance-check skill ──► check_compliance.py
        │        (checked against reference_architecture.md)
        ▼
provisioning_agent (router) ──uses──► provision-infra skill, Step 0
        │        (picks a path by the user's stated tool preference)
        ├──► cdk_provisioning_agent ──► aws-iac-mcp-server (design/validate)
        │                          └─► ccapi-mcp-server (execute via AWS
        │                              Cloud Control API)
        └──► terraform_provisioning_agent ──► HashiCorp Terraform MCP
                                          Server (create_run/action_run
                                          against HCP Terraform)
        │        each path produces a plain-English "Vibe Diff" first
        ▼
security_agent ──uses──► security-review-checklist skill
        │   (IAM + resource-type allow-list on the CDK path; workspace
        │    scope + an operator-controlled kill switch on the Terraform
        │    path; cost ceiling and region on both)
        ▼ (approved only)
   AWS (S3 + CloudFront, this MVP's demo scope)
```

**Multi-agent system (ADK).** Five distinct ADK agents, not one agent
wearing different hats via prompting: an orchestrator, a provisioning
*router*, two provisioning specialists (`cdk_provisioning_agent`,
`terraform_provisioning_agent`), and a Security Agent. The Security Agent
has *no* infrastructure-modifying tools available to it at all — it can
only approve or reject, so a prompt-injection or reasoning failure upstream
can't itself cause an unwanted change.

**Agent Skills.** We deliberately used Skills, not ad hoc prompt text, to
encode procedure: `provision-infra` (which path to take and how to execute
each), `security-review-checklist`, and `sdlc-diagram-compliance-check` are
each a `SKILL.md` with explicit trigger conditions and a numbered
procedure. This means the *how* of provisioning or reviewing is versioned,
inspectable, and reusable across whichever agent loads it.

**MCP Servers.** We use Skills for procedure and MCP for reach — and
specifically chose to *route to existing, officially maintained servers*
rather than write our own: AWS Labs' `aws-iac-mcp-server` (CDK/CloudFormation
docs, `cfn-lint`, `cfn-guard` — validation only, no execution) paired with
`ccapi-mcp-server` (the actual create/update/delete via AWS Cloud Control
API), or HashiCorp's official Terraform MCP Server for teams on HCP
Terraform. This is a stronger "clever use of existing toolsets" story than
a hand-rolled server, at the cost of a wider tool surface we had to
explicitly re-scope in the security review (see below).

## Security & Guardrails

Security isn't a bolt-on feature here, it's the reason the architecture is
split the way it is:

- **Least privilege by construction**: `infra/iam-policy.json` allow-lists
  exactly the actions our credentials need — nothing broader. The
  credentials used by the agent are scoped to this policy, not to a
  general-purpose account.
- **A second allow-list where IAM alone isn't enough**: `ccapi-mcp-server`'s
  tools accept an arbitrary CloudFormation-style resource type as a
  parameter, so being IAM-permitted to call its API doesn't by itself bound
  *which* resource types get touched. `infra/allowed-resource-types.json` is
  an application-level allow-list the Security Agent checks explicitly —
  we treat this as equally load-bearing as the IAM policy, not a
  nice-to-have, precisely because routing to a more powerful existing tool
  (CCAPI covers 1,100+ resource types) means we can't rely on IAM scoping
  alone the way our original narrow custom server did.
- **Defense in depth**: the Security Agent's review runs before any
  execution attempt; on the Terraform path, an `ENABLE_TF_OPERATIONS` flag
  is additionally required and can only be set by the human operator, never
  toggled by the agent itself — a second, independent gate on the riskiest
  operation.
- **Plain-English approval gate**: every provisioning action is preceded by
  a human-readable "Vibe Diff" summary of exactly what will be created and
  what it will cost, reviewed before execution — not after.
- **Cost ceiling as a hard stop**: `MAX_ESTIMATED_MONTHLY_COST_USD` is
  checked by the Security Agent on every plan; a plan that exceeds it is
  rejected, not flagged-and-continued.
- **Deterministic compliance checks**: `check_compliance.py` runs as a plain
  script, not a model call, specifically so its results are reproducible and
  can be included in an audit log without worrying about non-determinism.

## Deployability

The system is packaged so the ADK orchestrator can run as a long-lived
service (e.g., on Cloud Run or Vertex AI Agent Engine) with the MCP server
running as a local subprocess (stdio transport) alongside it, or as a
separately deployed remote MCP endpoint if we split the provisioning surface
out further. Because the Security Agent's review is a discrete, stateless
step, it's straightforward to trigger this whole flow from a CI/CD pipeline
— e.g., a GitHub Action that runs compliance checks and provisioning-plan
review on every infra-spec pull request, promoting only approved plans to a
manual "apply" step. [In the video: narrate this deployment path — we are
not required to stand up a live public endpoint for judging, and did not, to
keep the sandbox AWS account's footprint minimal and fully torn down after
recording.]

## Implementation & Technical Decisions

- **Stack**: Python, Google ADK for agent orchestration, plain YAML for the
  structured infra spec input. Notably, no `boto3` and no hand-written cloud
  SDK calls in this project's own code — provisioning routes entirely
  through third-party MCP servers (`aws-iac-mcp-server`, `ccapi-mcp-server`,
  HashiCorp's Terraform MCP Server) launched as subprocesses.
- **Why route to existing MCP servers instead of writing our own**: we
  researched what's already officially maintained before building anything
  — AWS Labs and HashiCorp both publish and actively maintain servers that
  cover far more of the CDK/CloudFormation and Terraform surface than we
  could build in the time we had, and staying current with provider APIs
  becomes their maintenance burden, not ours. The cost is a wider,
  less-bespoke tool surface, which is why the security review skill has
  explicit path-specific checks rather than one simple allow-list.
- **Why a structured spec instead of diagram image parsing for the MVP**:
  diagram-to-structure extraction is a real, separate problem (OCR/vision +
  disambiguation), and we didn't want to ship an unreliable version of it
  that undermines trust in the compliance check. We scoped the MVP to a
  structured YAML input and documented image parsing as the next increment
  rather than half-build it.
- **Why static-site provisioning as the first surface**: it's a small,
  well-bounded AWS action set (S3 + CloudFront) that lets us fully exercise
  the review → approve → execute → verify loop without the larger blast
  radius of compute-provisioning actions (Lambda/ECS/EC2), which is the
  natural next surface to add behind the same architecture.
- **Why the Security Agent has no tools**: this was a deliberate choice —
  giving the reviewing agent the *ability* to also execute actions would
  undermine the separation-of-duties property we wanted the architecture to
  guarantee.

## Demo Walkthrough

[Fill in after running the real demo. Suggested walkthrough beat-by-beat,
matching `spec/example_submission.yaml`:]

1. Submit a request to deploy a static blog site (`demo-blog`, `us-east-1`,
   low traffic tier), stating a tool preference — e.g. "using CDK, deploy...".
2. `sdlc-diagram-compliance-check` runs against the spec — PASS, with the
   specific rules checked shown in the output.
3. `provisioning_agent` routes to `cdk_provisioning_agent`, which validates
   a CloudFormation template via `aws-iac-mcp-server` and produces the
   plain-English Vibe Diff summary: resource types, region, estimated cost.
4. Security Agent reviews against `infra/iam-policy.json`,
   `infra/allowed-resource-types.json`, and the cost ceiling — approves.
5. `ccapi-mcp-server` creates the S3 bucket + CloudFront distribution; the
   agent reports back the resulting URL.
6. [Optional] Repeat the same request with "using Terraform" instead, to
   show the routing actually switches provisioning sub-agent and toolchain.
7. [Optional] Show a *rejected* case — e.g., a spec requesting public write
   access on the bucket — to demonstrate the compliance check and security
   review actually blocking a real violation, not just a happy path.

## Business Value & Impact

This collapses what's typically a multi-day, multi-person ticket cycle
(request → architecture review → security review → provisioning → 
verification) into a single reviewable flow, while keeping a human-legible
approval point rather than removing oversight entirely. For teams without a
dedicated platform org, this is the difference between having infra
guardrails at all and not. For larger orgs, it's a way to make compliance
review continuous and auditable instead of a periodic, backlogged process.

## Challenges & Learnings

The hardest design question was where to put the trust boundary — it would
have been easy to let one agent "own" both plan-drafting and execution and
just prompt it to be careful. We chose the harder path of a separate
reviewing agent with no execution capability, plus checks duplicated at the
MCP layer, because a system that provisions real infrastructure needs
guarantees that don't depend entirely on prompt compliance. [Add real
challenges encountered once you run the build — e.g., anything you hit with
ADK's MCP integration API, IAM policy tuning against your sandbox account,
or CloudFront API details.]

## Roadmap

This is intentionally a minimal, extensible core. We researched the current
MCP ecosystem specifically so the next contributor doesn't have to:
- **GCP**: Google's managed MCP servers (50+, GA/preview as of Google Cloud
  Next '26) — specifically the GCE MCP server for compute provisioning.
- **Azure**: Azure MCP Server 2.0 (self-hosted/remote, 276 tools across 57
  services) or the newer Azure Resource Manager MCP Server for
  CloudFormation-style declarative parity with our CDK path.
- **Terraform on GCP/Azure**: no new server needed — HashiCorp's server is
  already cloud-agnostic via Terraform providers, so this is a config change,
  not a new integration.
- Diagram image upload → vision-based structured spec extraction, feeding
  the same `check_compliance.py`.
- Additional AWS provisioning surfaces (compute, networking) behind the same
  review/approval pattern.
- Distributed agents behind an Agent-to-Agent (A2A) protocol with individual
  Agent Cards, so the Security/Compliance agent could be a shared service
  reused across multiple provisioning agents/teams, not just this one.
- A messaging-app input surface (Slack/Teams) so requests can be submitted
  conversationally, reusing this same orchestration underneath.

## Conclusion

PlatformOps Agent shows that agentic judgment and safe, real-world action
aren't in tension if you architect for it: skills for procedure, a narrow
MCP server for reach, and a non-executing security reviewer as a hard gate
in between. We built the smallest version of this that's real — not
simulated — and designed every seam so the next surface (more resource
types, real diagrams, more clouds) plugs into the same pattern.

---

**Public Project Link**: https://github.com/kadimetla/PlatformOps
(setup instructions in README.md)
**Video**: [YouTube URL, ≤5 min]
**Cover image**: [architecture diagram from this writeup, as an image asset]
