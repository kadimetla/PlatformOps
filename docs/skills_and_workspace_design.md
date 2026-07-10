# Workspace Files, Skill Precedence, and Skill-Authoring — Design

## Status
Analysis and design only — **nothing in this document is built**. That
includes the *bundled* tier this precedence hierarchy sits on top of —
see `docs/skill_loading_and_enforcement_gap.md` for the finding that no
code today loads a `SKILL.md`'s content or enforces its `allowed-tools`,
which the precedence/authoring design below implicitly assumes works.
It goes
one level deeper than `docs/ui_and_multitenancy_deep_dive.md`'s Org → BU →
team-member mapping, which this doc doesn't repeat — read that one first
for the tenancy model this builds on. This doc covers three things that
weren't designed anywhere yet: what OpenClaw's workspace *files*
concretely become for PlatformOps, how skill precedence should work across
bundled/org/BU, and — the genuinely new piece — what happens when no
existing skill matches a request and one has to be authored.

## Part A: Workspace file → PlatformOps mapping (concrete layout)

Given a BU = one `agent_id` = one workspace (established in
`docs/HARNESS_DESIGN.md`), here's the concrete directory shape, at all
three tiers:

```
skills/                          # bundled/global — lowest precedence
  provision-infra/SKILL.md
  security-review-checklist/SKILL.md
  sdlc-diagram-compliance-check/SKILL.md

orgs/<org_id>/                   # org-level — mid precedence
  AGENTS.md                      # org-wide policy, e.g. mandatory tagging
  SOUL.md                        # org-wide default tone
  skills/                        # org-level skill overrides

workspaces/<agent_id>/           # BU-level — highest precedence
  AGENTS.md                      # BU-specific rules (change-freeze windows, escalation)
  SOUL.md                        # inherited from org unless overridden
  TEAM.md                        # repurposed USER.md — see below
  IDENTITY.md
  TOOLS.md                       # guidance only, not enforcement
  BOOTSTRAP.md                   # BU onboarding ritual, deleted after first run
  memory/YYYY-MM-DD.md           # see docs/harness_memory_design.md
  MEMORY.md                      # see docs/harness_memory_design.md
  skills/                        # BU-level skill overrides
```

### Why `USER.md` becomes `TEAM.md`, not a direct port
OpenClaw's `USER.md` assumes one persistent user per agent — *"who the
user is and how to address them."* PlatformOps has many people per BU, so
this file is repurposed to team/BU-level context (who to notify, primary
contact) rather than one person's profile. Individual identity is tracked
separately — see "Team member roles" below — because workspace files load
identically regardless of which team member sent the request, and
per-person behavior (who can approve, who's an admin) has to vary by
request, not by workspace.

### `TOOLS.md` stays guidance, never enforcement
Per OpenClaw's own caveat, `TOOLS.md` "does not control tool availability;
it is only guidance." Same rule here: a BU's `TOOLS.md` might say "we
prefer CDK," but `infra/allowed-resource-types.json` and
`harness/tool_dispatcher.py` remain the only things that actually gate
what can execute. This is the same guidance-vs-enforcement distinction
already made throughout `docs/current_architecture.md`.

### `BOOTSTRAP.md` → BU onboarding, a concrete answer to an open item
`docs/HARNESS_DESIGN.md`'s "org registry + onboarding automation" has been
an open item with no concrete shape. This gives it one: a `BOOTSTRAP.md`-
equivalent ritual, run once when a new `agent_id` is minted, collecting
cloud account, initial `allowed_resource_types`, initial cost ceiling, and
initial team roster — then deleted/marked complete, exactly like
OpenClaw's own pattern.

### Team member roles (new, small schema)
Not a workspace file — a small addition to `WorkspaceBundle`
(`harness/schemas.py`), sketched here, not yet implemented:

```python
class TeamMember(BaseModel):
    channel_user_id: str
    display_name: str
    role: str   # "requester" | "approver" | "admin"
    scope: str  # "foundation" | "app" | "both" — see below

# Added to WorkspaceBundle:
members: list[TeamMember] = Field(default_factory=list)
```

This is what a review policy would check against when deciding whether
`ApprovalRecord.human_reviewer` (== some `channel_user_id`) was actually
allowed to approve — today nothing checks this at all.

**`scope` added by later research** (see
`docs/infra_discovery_and_platform_app_split.md` Part C) — `role` alone
conflates "how much authority" with "over what." A platform engineer and
an app developer at the same BU need genuinely different access, not
just different amounts of the same access: someone can be
`role="admin", scope="app"` — full control over their own app-layer
deploys — with zero access to foundation-layer changes (VPC/EKS)
regardless of role. `scope` is that orthogonal axis, checked
independently of `role`.

## Part B: Skill precedence — bundled → org → BU

OpenClaw's own precedence (workspace > project > personal > managed >
bundled) is the right *shape* for "AWS skills reusable across orgs, but
org/BU can override" — adapted down to our two-level tenancy:

```
BU workspace skills   (highest precedence)
        ↓ overrides
Org-level skills
        ↓ overrides
Bundled/global skills (lowest precedence — shared baseline, what exists today)
```

**Resolution order** for a given request (sketch, not yet implemented):
```python
def resolve_skill(request_text: str, bu_id: str, org_id: str) -> SkillMatch | None:
    for tier_dir in [f"workspaces/{bu_id}/skills", f"orgs/{org_id}/skills", "skills"]:
        match = find_matching_skill(tier_dir, request_text)
        if match:
            return match
    return None  # no existing skill — see Part C
```

`find_matching_skill` for the MVP is just trigger-phrase matching against
each `SKILL.md`'s frontmatter `description` — the same mechanism already
in use today. This has an honest scaling limit worth stating now rather
than discovering later: exact/fuzzy string matching is fine for a handful
of skills per tier, but once a BU accumulates dozens of authored skills
(see Part C), semantic/embedding-based matching becomes necessary. Not
needed for the current build; worth flagging so nobody's surprised later.

**Deliberate divergence from OpenClaw**: no individual/"personal" tier.
OpenClaw has one (personal agent skills); PlatformOps intentionally
doesn't. Letting one person carry personal skill overrides that bypass
BU-level security rules would undermine the entire governance model this
project depends on. Skills stop at the BU boundary.

## Part C: Skill-authoring — what happens when nothing matches

This is the genuinely new design, not a refinement of anything already
documented.

### The workflow
1. `resolve_skill()` returns nothing.
2. An agent drafts new IaC (CDK/Terraform) for the request — same
   drafting behavior as today, nothing new here.
3. **New**: instead of the draft simply being this request's one-off plan,
   it can optionally become a `SkillProposal` — a candidate for reuse next
   time this trigger phrase comes up.

### Why this needs its own approval gate, not a shortcut
An agent that can both invent a new pattern *and* have future runs trust
it automatically is a skill-injection risk: one bad or hallucinated
authoring run could poison the skill library for every future request
that matches its trigger phrase, at a BU that may run this pattern
unattended for months. This deserves the same discipline as `ToolIntent`,
not less.

### `SkillProposal` (sketch, not yet implemented — matches the style of `harness/schemas.py`)
```python
class SkillProposal(BaseModel):
    proposal_id: str
    org_id: str
    bu_id: str
    source_plan_id: str            # which PlanRecord/request originated this
    trigger_description: str       # candidate SKILL.md frontmatter description
    draft_skill_md: str             # the drafted SKILL.md content
    draft_iac_snippet: str          # the drafted CDK/Terraform backing it
    status: str = "pending"         # pending | approved | rejected
    reviewer: Optional[str] = None  # channel_user_id; required for approval
    approved_at: Optional[datetime.datetime] = None
    version: int = 1
    promoted_to: Optional[str] = None  # None | "org" | "bundled"
```

### Materialization and promotion
1. A `SkillProposal` starts scoped to the originating BU only — never
   auto-promoted to org or bundled level. A pattern novel to one BU isn't
   necessarily reviewed or appropriate for others.
2. A human reviewer (a BU `TeamMember` with `role="approver"` or
   `"admin"`) reviews `draft_skill_md` + `draft_iac_snippet` — same shape
   as `ApprovalRecord.human_approved`, applied to a skill instead of a
   cloud change.
3. On approval, it's materialized as a real skill at
   `workspaces/<agent_id>/skills/<name>/SKILL.md`, `version=1`.
4. **Promotion upward (BU → org, or org → bundled) is a separate,
   higher-bar action**, not automatic — proposed criteria: usage evidence
   (successfully used N times at the narrower scope), a review
   specifically for over-fitting to BU-specific assumptions that would be
   wrong elsewhere, and explicit sign-off from an org/global owner. This
   is closer to a PR/code-review process than an approval click.
   **N is now specified**: `docs/skill_promotion_thresholds.md` gives
   this a concrete, sourced value (3 consecutive successes, not a raw
   cumulative count) plus a demotion path this bullet never had.
5. **Versioning**: if a promoted/shared skill is later found flawed,
   silently changing the pattern underneath BUs already using it is
   itself a risky, supply-chain-shaped operation. BUs should stay pinned
   to the version they adopted unless they explicitly opt into an
   upgrade — echoing `docs/harness_deep_dive.md`'s existing note that
   "plugin install/update should be version-pinned," applied here to
   skills instead of plugins.

## Open questions / not yet decided
- Where do `SkillProposal` records actually persist — same SQLite file as
  `harness/tool_dispatcher.py`'s audit/approval tables, or separate
  storage? Leaning toward same store, not yet decided.
- What triggers promotion review — a manual request, or an automatic
  flag once a BU-level skill crosses a usage threshold? Not yet decided.
- Semantic/embedding-based skill matching (Part B) needs a concrete
  technology choice once it's actually needed — not urgent now.

## How this relates to the existing docs
- Builds on, doesn't repeat, `docs/ui_and_multitenancy_deep_dive.md`'s
  Org → BU → team-member mapping.
- The `TeamMember`/`members` addition to `WorkspaceBundle` is the same
  audit-gap concern raised there (`channel_user_id` missing from
  `harness/tool_dispatcher.py`'s audit log) — fixing that gap and adding
  `members` are naturally the same piece of work.
- Doesn't change the one required next step
  (`plan_request(envelope)` in `docs/planned_implementation.md` Phase 3)
  — skill-authoring is a layer on top of that, usable once it exists, not
  a prerequisite for it.
