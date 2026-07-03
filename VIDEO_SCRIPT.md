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
- [ ] Have `agents/`, `skills/*/SKILL.md`, `mcp_server/aws_mcp_server.py`,
      `infra/iam-policy.json` open and ready to flash on screen during "The
      Build"

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
> If it passes, the Provisioning Agent — a distinct ADK agent — drafts a
> plan and produces a plain-English summary of exactly what it's about to
> create, before touching anything.
>
> That plan goes to a separate Security Agent for review. This agent has no
> AWS tools at all — it can only approve or reject, checking the plan
> against our IAM allow-list and cost ceiling. That's a deliberate
> separation of duties: a compromised or confused agent upstream can't
> execute anything on its own.
>
> Only an approved plan reaches our MCP server, which exposes exactly three
> AWS actions — estimate cost, create the site, check status — and
> re-checks the same allow-list and cost ceiling itself before doing
> anything. Two independent checkpoints, not one."

---

## 2:30–4:00 — Demo (90s)

**Visual:** Screen recording, sped up where there's dead air (e.g., waiting
on AWS API calls), real-time for the interesting parts (the Vibe Diff
summary appearing, the approval, the rejected case).

**VO (adjust to match what's actually on screen):**
> "Here's a real run. I ask for a static blog site in us-east-1. The
> compliance check passes — you can see exactly which rules it verified.
> The Provisioning Agent estimates cost at about a dollar a month and shows
> the plain-English summary of what it's about to create. The Security
> Agent reviews it against our policy and approves. The MCP server creates
> the S3 bucket and CloudFront distribution, and we get back a working URL.
>
> Now here's a spec that requests public write access on the bucket — [show
> rejection]. The compliance check catches it immediately, with the specific
> rule it violates. Nothing gets provisioned. This is the same system
> refusing to do something unsafe, not just a happy-path demo."

---

## 4:00–5:00 — The Build (60s)

**Visual:** Quick cuts across the actual file tree / code: `agents/`
folder, one `SKILL.md` open, `aws_mcp_server.py`, `infra/iam-policy.json`.

**VO:**
> "Under the hood: Google's Agent Development Kit for multi-agent
> orchestration, with three distinct agents — orchestrator, provisioning,
> and security — not one agent role-playing different jobs. Procedure lives
> in Agent Skills: versioned, inspectable markdown files an ops team could
> edit without touching code. Reach lives in a purpose-built MCP server with
> a deliberately narrow tool surface. And least-privilege IAM plus a hard
> cost ceiling are enforced at two independent layers, not just one.
>
> This is a minimal, real, working core — not a mockup — designed so the
> next surface, like real diagram parsing or compute provisioning, plugs
> into the exact same review-and-approve pattern."

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
