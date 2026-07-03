<!--
YouTube video script — target 4:45-5:00 total (hard cap 5:00).
Timings are budgets, not exact cues — practice a read-through and trim, don't
pad. Bracketed [ ] = something you need to record/insert; VO = voiceover line.
-->

# Video Script — PlatformOps Agent (target: 4:45)

## Recording checklist (do these BEFORE scripting the final cut)
- [ ] Screen recording: golden-path run (`demo-blog` spec → compliance PASS →
      Vibe Diff summary → security approval → resources created → URL
      returned)
- [ ] Screen recording: one **rejected** case (e.g. public-write S3 spec) —
      compliance check or security review actually blocking it
- [ ] Static image/export of the architecture diagram (from README.md /
      WRITEUP.md) — make it legible at video resolution, don't just screenshot
      the markdown
- [ ] Screen recording: the same request re-run with "using Terraform"
      instead of "using CDK" — shows the router actually switching
      provisioning sub-agent and toolchain, not just a hardcoded path
- [ ] Have `agents/`, `skills/*/SKILL.md`, `mcp_server/external_servers.py`,
      `infra/iam-policy.json`, `infra/allowed-resource-types.json` open and
      ready to flash on screen during "The Build"

---

## 0:00–0:30 — Problem (30s)

**Visual:** Talking head or simple title card, then a quick diagram/animation
of the manual flow: request → ticket → review → provisioning → compliance
check, each step taking days.

**VO:**
> "Every company running workloads on AWS needs a platform ops team to turn
> requirements into provisioned, secure infrastructure. In practice, that's
> tickets, manual review, and compliance checks that lag behind what's
> actually deployed. Teams without a dedicated ops function either skip
> these guardrails, or burn engineering time they don't have. We built an
> agent that does this job — and makes every step of it auditable."

---

## 0:30–1:00 — Why Agents (30s)

**Visual:** Simple on-screen text callouts as you speak: "judgment, not a
fixed pipeline" / "procedure vs. reach."

**VO:**
> "This isn't a scripting problem — deciding if a spec is compliant, or if a
> provisioning plan is safe to run, takes judgment applied to unstructured
> input. Agents let us separate *procedure* — what to check and in what
> order — from *reach* — the actual ability to touch AWS. That separation is
> the core of the architecture, and it's what let us build in real safety
> guarantees instead of just hoping the model behaves."

---

## 1:00–2:30 — Architecture (90s)

**Visual:** Full-screen architecture diagram (the one from README.md),
built up piece by piece as you narrate each stage — don't just show it
static for 90 seconds, animate/reveal it in sync with the VO.

**VO:**
> "A request comes in as a structured spec. First, the SDLC compliance skill
> checks it against our reference architecture — rules like 'no public
> write access,' 'HTTPS enforced,' 'stay within the approved region and
> cost ceiling.' That check is deterministic code, not a model call, so the
> result is reproducible and auditable.
>
> If it passes, a provisioning router agent picks a path based on the
> user's tool preference — CDK-native, or Terraform. Rather than writing
> our own AWS provisioning code, each path routes to an existing, officially
> maintained MCP server: AWS Labs' tools for CDK and AWS's Cloud Control
> API, or HashiCorp's official Terraform MCP Server for teams on HCP
> Terraform. Both produce a plain-English summary of exactly what they're
> about to create, before touching anything.
>
> That plan goes to a separate Security Agent for review. This agent has no
> infrastructure-modifying tools at all — it can only approve or reject.
> Because one of these tools can touch over a thousand resource types, IAM
> permissions alone aren't a tight enough boundary, so the Security Agent
> also checks the plan against an explicit resource-type allow-list — a
> second, independent gate.
>
> Only an approved plan executes. Two independent checkpoints, not one, on
> the riskiest step in the system."

---

## 2:30–4:00 — Demo (90s)

**Visual:** Screen recording, sped up where there's dead air (e.g., waiting
on AWS API calls), real-time for the interesting parts (the Vibe Diff
summary appearing, the approval, the rejected case).

**VO (adjust to match what's actually on screen):**
> "Here's a real run. I ask for a static blog site in us-east-1, using CDK.
> The compliance check passes — you can see exactly which rules it verified.
> The CDK provisioning agent validates the template and shows a plain-English
> summary of what it's about to create. The Security Agent reviews it and
> approves. The resources get created via AWS's Cloud Control API, and we
> get back a working URL.
>
> Now the same request, but 'using Terraform' instead — [show it routing to
> the Terraform agent]. Same review, same approval gate, different
> execution path underneath.
>
> Now here's a spec that requests public write access on the bucket — [show
> rejection]. The compliance check catches it immediately, with the specific
> rule it violates. Nothing gets provisioned. This is the same system
> refusing to do something unsafe, not just a happy-path demo."

---

## 4:00–5:00 — The Build (60s)

**Visual:** Quick cuts across the actual file tree / code: `agents/`
folder, one `SKILL.md` open, `mcp_server/external_servers.py`,
`infra/iam-policy.json`, `infra/allowed-resource-types.json`.

**VO:**
> "Under the hood: Google's Agent Development Kit for multi-agent
> orchestration, with five distinct agents — an orchestrator, a
> provisioning router, two provisioning specialists, and security — not one
> agent role-playing different jobs. Procedure lives in Agent Skills:
> versioned, inspectable markdown files an ops team could edit without
> touching code. Reach lives entirely in existing, officially maintained MCP
> servers — we deliberately didn't write our own AWS provisioning code.
> And least-privilege IAM plus a resource-type allow-list plus a hard cost
> ceiling are enforced at independent layers, not just one.
>
> This is a minimal, real, working core — not a mockup — designed so the
> next surface, like GCP, Azure, or real diagram parsing, plugs into the
> exact same review-and-approve pattern. We researched the current MCP
> ecosystem for those too — it's in the README roadmap."

---

## Timing summary
| Section | Budget | Cumulative |
|---|---|---|
| Problem | 0:30 | 0:30 |
| Why Agents | 0:30 | 1:00 |
| Architecture | 1:30 | 2:30 |
| Demo | 1:30 | 4:00 |
| The Build | 1:00 | 5:00 |

Leave yourself ~10-15s of buffer under 5:00 for editing slop (intro title
card, outro card with the repo link) — aim to finish narration by 4:45.
