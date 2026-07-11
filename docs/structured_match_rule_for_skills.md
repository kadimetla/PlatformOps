---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: what makes a skill match "structured enough" to skip the LLM — resolves docs/deterministic_plan_drafting.md's open question
reviewed_by: unreviewed (first draft)
---

# The Structured-Match Rule — When a Skill Match Can Skip the LLM Entirely

## Status
Design only, grounded in this project's own real code and existing
docs — no external research needed, this is internal synthesis, not a
third-party-tool claim. Resolves `docs/deterministic_plan_drafting.md`'s
open question (*"what exactly makes a skill match 'structured enough'
to skip the LLM"*) and, along the way, surfaces and designs a real gap:
`envelope_to_spec(envelope)` has been referenced by name in two docs'
code sketches since `docs/plan_request_verified_implementation.md` but
was never actually designed. Nothing here is built.

## Part A: The gap this starts from
Grepped the repo for `envelope_to_spec` — it appears exactly twice,
both as an uncommented placeholder call inside doc code blocks
(`docs/plan_request_verified_implementation.md`,
`docs/deterministic_plan_drafting.md`), never defined. Meanwhile
`spec/check_compliance.py#check_compliance(spec: dict)` is real,
tested code requiring a structured `dict` — but `RequestEnvelope.raw_payload`
(`harness/schemas.py:21`) is a bare `str`. Nothing in this project has
ever defined how one becomes the other, despite `plan_request(envelope)`
depending on it as its very first step. This gap turns out to be most
of the structured-match question, not a separate one — "is this request
structured enough to skip the LLM" and "how does a raw request become
the structured spec compliance-checking needs" are the same question.

## Part B: This project already has a structured-request format — reuse it
`spec/example_submission.yaml` (real, used by `check_compliance.py`'s
own `__main__` block) is already this project's structured-request
shape:
```yaml
app_name: demo-blog
region: us-east-1
estimated_monthly_usd: 1.0
resources:
  - type: s3_bucket
    name: platformops-demo-blog
    public_write: false
  - type: cloudfront_distribution
    name: platformops-demo-blog-cdn
    viewer_protocol_policy: redirect-to-https
```
The structured-match rule should target *this* shape, not invent a
second one. A webhook payload, a CLI `--spec-file`, or a Control UI form
that already serializes to this YAML is "structured" by construction;
free-form Slack/CLI chat text is not, and needs a conversion step first.

## Part C: Phase 1 — `envelope_to_spec`, deterministic-first
```python
def envelope_to_spec(envelope: RequestEnvelope) -> dict:
    try:
        candidate = yaml.safe_load(envelope.raw_payload)
        if is_valid_spec_shape(candidate):   # deterministic schema check
            return candidate                 # against Part B's shape
    except yaml.YAMLError:
        pass
    # Reached only for genuine free text. One cheap, routing-tier,
    # structured-output-only call — NOT root_agent's full drafting
    # graph. A narrower extraction_agent, same model tier as this
    # project's existing "routing" role (config/models.yaml).
    return extract_spec_from_free_text(envelope.raw_payload)
```
`is_valid_spec_shape()` is itself deterministic — a schema check against
Part B's shape (required top-level keys, `resources` is a list of dicts
each with a `type`), not an LLM judgment call. This answers
`docs/deterministic_plan_drafting.md`'s open question about whether
free-text input needs an LLM before the deterministic branch can even
be attempted: **yes, but only a single small extraction call, not a
fallback to the full agent graph** — the extraction call's only job is
producing the `spec` dict; everything after that point, including
whether a skill matches, stays deterministic regardless of how `spec`
was produced.

## Part D: Phase 2 — `check_structured_match`, fully deterministic
```python
class SkillMatch(BaseModel):
    skill: Optional[SkillProposal] = None
    spec: dict
    has_structured_match: bool
    missing_vars: list[str] = Field(default_factory=list)
    ambiguous_candidates: list[str] = Field(default_factory=list)

def check_structured_match(
    spec: dict, bu_id: str, org_id: str, bundle: WorkspaceBundle
) -> SkillMatch:
    candidates = resolve_skill_candidates(spec, bu_id, org_id)  # tier-precedence
                                                                  # search, unchanged
                                                                  # from docs/skills_and_workspace_design.md
    if len(candidates) != 1:
        return SkillMatch(
            spec=spec, has_structured_match=False,
            ambiguous_candidates=[c.name for c in candidates],
        )
    skill = candidates[0]
    required = parse_declared_variables(skill.draft_iac_template)  # Terraform's
                                                                     # variables.tf, or
                                                                     # CFN's Parameters:
                                                                     # block — see Part F
    missing = [
        v.name for v in required
        if v.name not in spec and v.default is None and not hasattr(bundle, v.name)
    ]
    return SkillMatch(
        skill=skill, spec=spec,
        has_structured_match=not missing, missing_vars=missing,
    )
```
`plan_request()` then reads as a straight-line extension of
`docs/deterministic_plan_drafting.md`'s Part D, with the placeholder
`has_structured_match` now concretely produced:
```python
spec = envelope_to_spec(envelope)
failures = check_compliance(spec)
if failures:
    raise ComplianceError(failures)
match = check_structured_match(spec, envelope.bu_id, envelope.org_id, workspace_bundle)
agent = SkillTemplateFillAgent(match.skill, match.spec) if match.has_structured_match else root_agent
```

## Part E: The rule's actual content, stated precisely
1. **Zero or multiple candidate skills is never "structured."** Ambiguity
   is never guessed through — both cases fall back to `root_agent`,
   which can ask a clarifying question or draft fresh, rather than the
   deterministic path silently picking one. This is deny-by-default's
   shape applied to skill selection, not just cloud mutation.
2. **Every required template variable must resolve from exactly three
   sources**: the structured `spec` dict, the variable's own declared
   default, or `WorkspaceBundle` (region, cost ceiling — already-trusted
   config, not user input). Anything else missing means not structured.
3. **"Required" and type/constraint validity are read from the
   toolchain's own declaration syntax, never reinvented** — see Part F.
4. **A Layer 1 failure inside `SkillTemplateFillAgent` does not
   silently fall back to `root_agent`.** It surfaces as a drafting
   failure to the requester, the same way a failed `SmokeTestResult`
   blocks and waits for a human rather than auto-escalating to a
   different mechanism (`docs/post_apply_smoke_testing.md`). Chaining
   mechanisms silently after a failure would make it harder to tell
   which one actually produced a given plan.

## Part F0: `resolve_skill_candidates()`'s matching signal — verified, not `SkillToolset`
The open question below (originally: "leaning toward yes, a new
explicit field, not decided") is now settled, by direct package
inspection of `google-adk==2.4.0` rather than a leaning:

```python
class SkillRegistry(ABC):
  @abstractmethod
  async def search_skills(self, *, query: str) -> list[Frontmatter]: ...
```
`search_skills` is an **abstract method** — ADK ships zero built-in
matching logic. Whatever a concrete registry does (keyword, embedding,
exact) is bring-your-own. More importantly, `SearchSkillsTool` (the
concrete tool exposed to the agent) takes `args: {"query": str}` — the
**LLM** decides when to call it and what free-text query to pass. And
even for skills already resident in `SkillToolset(skills=[matched_skill])`
(this project's own existing sketch, no `search_skills` call involved
at all), *using* one still routes through the agent's system
instruction: *"if a skill seems relevant to the current user query, you
MUST use the `load_skill` tool"* — an LLM judgment call every time,
with no deterministic branch anywhere in the mechanism.

**Correction this forces**: `docs/plan_request_verified_implementation.md`
Part B characterized `SkillRegistry.search_skills()`/`.get_skill()` as
*"essentially `resolve_skill()` already implemented."* True only for
the LLM-mediated path. For `check_structured_match()`'s candidate
resolution specifically, `SkillToolset`/`SkillRegistry` can't be reused
at all — going through it means an LLM tool-call decision, structurally
incompatible with a zero-LLM-call branch. `resolve_skill_candidates()`
has to be a wholly separate, harness-owned function bypassing ADK's
skill machinery entirely, reusing only the bundled→org→BU **tier
directory order** from `docs/skills_and_workspace_design.md`, not its
skill-loading mechanism.

**The matching key**: `infra/allowed-resource-types.json` (real,
existing) already establishes this project's canonical resource-type
convention — CFN-style (`AWS::S3::Bucket`, `AWS::CloudFront::Distribution`),
also used by `ToolIntent.resource_type` (`harness/schemas.py:72`). But
`spec/example_submission.yaml`/`check_compliance.py` (also real) use a
different, lowercase convention (`s3_bucket`, `cloudfront_distribution`)
for the same resources — a genuine existing inconsistency, not
something to invent around. A new `SkillProposal.resource_types: list[str]`
field, CFN-style, bridges to `spec` via a small deterministic alias
table:
```python
SPEC_TYPE_TO_CFN_TYPE = {
    "s3_bucket": "AWS::S3::Bucket",
    "cloudfront_distribution": "AWS::CloudFront::Distribution",
    # extended per infra/allowed-resource-types.json as new types are added
}

def resolve_skill_candidates(spec: dict, bu_id: str, org_id: str) -> list[SkillProposal]:
    normalized = {SPEC_TYPE_TO_CFN_TYPE[r["type"]] for r in spec["resources"]}
    for tier_dir in [f"workspaces/{bu_id}/skills", f"orgs/{org_id}/skills", "skills"]:
        matches = [s for s in load_skills_in_tier(tier_dir)
                   if set(s.resource_types) == normalized]  # exact SET match,
                                                              # not superset,
                                                              # not per-resource
        if matches:
            return matches   # stop at first tier with any match — precedence preserved
    return []
```
Two deliberate constraints:
- **Exact set match, not superset or per-resource composition.** A
  skill declaring `resource_types=["AWS::S3::Bucket", "AWS::CloudFront::Distribution"]`
  only matches a request needing exactly those two, nothing more or
  fewer. Multi-skill composition (combining separately-matched
  fragments, ordering dependencies between them) stays a `root_agent`
  problem — the deterministic path stays narrow rather than
  half-solving a harder problem.
- **Ambiguity within the winning tier still fails closed** — two
  BU-tier skills both matching doesn't fall through to org/bundled to
  break the tie; falling through would conflate precedence (resolves
  cross-tier conflicts) with disambiguation (which this rule never does
  automatically, per Part E rule 1).

## Part F0b: `load_skills_in_tier()`, verified — a real two-phase mechanism, not one placeholder
Part F0's `load_skills_in_tier(tier_dir)` was itself a placeholder name.
Verified directly against `google-adk==2.4.0`:
```python
list_skills_in_dir(skills_base_path: str | Path) -> dict[str, Frontmatter]
load_skill_from_dir(skill_dir: str | Path) -> Skill
```
`list_skills_in_dir` is **cheap and frontmatter-only** — it reads just
each skill's YAML frontmatter (`_read_skill_properties`), not the full
`SKILL.md` body or bundled `scripts/`. It's **non-recursive, one
directory level**: `for skill_dir in sorted(skills_base_path.iterdir())`,
each immediate subdirectory is one skill, `skill_id` = directory name —
matches this repo's actual layout (`skills/provision-infra/`,
`skills/security-review-checklist/`) exactly, no restructuring implied.

This means `resolve_skill_candidates()` is genuinely **two phases**, not
the flat single-pass loop Part F0 sketched:
```python
def load_skills_in_tier(tier_dir: str) -> dict[str, Frontmatter]:
    return list_skills_in_dir(tier_dir)   # real ADK function, cheap — frontmatter only

def resolve_skill_candidates(spec: dict, bu_id: str, org_id: str) -> list[Skill]:
    normalized = {SPEC_TYPE_TO_CFN_TYPE[r["type"]] for r in spec["resources"]}
    for tier_dir in [f"workspaces/{bu_id}/skills", f"orgs/{org_id}/skills", "skills"]:
        frontmatters = load_skills_in_tier(tier_dir)                    # phase 1: cheap
        matching_ids = [sid for sid, fm in frontmatters.items()
                         if set(fm.metadata.get("resource_types", [])) == normalized]
        if len(matching_ids) == 1:
            return [load_skill_from_dir(f"{tier_dir}/{matching_ids[0]}")]  # phase 2: one full load
        if matching_ids:
            return []   # ambiguous — fails closed per Part E rule 1, zero full loads spent
    return []
```
`resource_types` lives in `Frontmatter.metadata["resource_types"]` —
readable during the cheap phase 1, so the expensive full
`load_skill_from_dir()` (pulling in `draft_iac_template`/instructions/
bundled resources) only ever runs on the single winning candidate, never
on every skill in a tier.

**A silent reconnection to the `allowed-tools` bug fixed earlier this
project** (`docs/plan_request_verified_implementation.md` Part C):
`list_skills_in_dir` catches `FileNotFoundError, ValueError,
ValidationError` *per skill* and just logs a warning, skipping the bad
skill rather than raising. Before that fix, all three of this project's
real `SKILL.md` files had invalid `allowed-tools` YAML — meaning
`list_skills_in_dir("skills")` would have silently returned an **empty
dict** for the entire bundled tier, always. `resolve_skill_candidates()`
built on top of that would have returned zero candidates for every
request, forever, silently falling back to `root_agent` every time, with
nothing but a warning log to explain why. That fix wasn't only about one
direct `load_skill_from_dir()` call — it was silently load-bearing for
this entire deterministic-matching design before the design existed.

**A new failure mode Part E didn't cover**: `load_skill_from_dir`
(phase 2, the winner) *raises* — `FileNotFoundError`/`ValueError` — for
a skill that passed the cheap frontmatter check but has a corrupted body
or a missing referenced resource file. Different from "ambiguous" or
"no match." Same fail-closed answer as everything else here: log loudly,
fall back to `root_agent`, not a hard crash — but genuinely a third,
distinct case (frontmatter-valid, body-invalid), not folded automatically
into Part E's existing two rules.

**Performance, not yet designed as a hard rule**: `resolve_skill_candidates()`
sits on the hot path for every request, before any `Runner` is
constructed — three real directory walks per request (one per tier)
isn't free at scale. Rather than a new caching mechanism, this should
reuse `docs/HARNESS_DESIGN.md`'s existing config-reload discipline
(*"keep the last accepted config active if reload fails"*): an in-memory
per-tier `dict[str, Frontmatter]` index, rebuilt via `list_skills_in_dir()`
on a reload trigger, not walked fresh per request.

## Part F0c: Caching tier loading — two layers, two different policies
Designing the cache for Part F0b's directory walks surfaced a real gap
in Part F0/F0b's own matching filter, not just a performance question:
`resolve_skill_candidates()` as designed so far checks `resource_types`
only — it never checks whether the matched skill is still *trusted*.
That turns out to be the more important finding here.

**Layer 1 — `Frontmatter`/`resource_types`, from `list_skills_in_dir()`.**
Changes rarely, only on `SkillProposal` materialization
(`docs/skills_and_workspace_design.md` Part A step 5). Cache as an
in-memory `dict[tier_dir, dict[skill_id, Frontmatter]]`, loaded at
process startup the same way `ConfigLoader.load_and_validate()`
(`harness/config_engine.py`) loads bundles/bindings — worth being
precise that the real `ConfigLoader` today just raises on validation
failure, it does **not** yet implement the atomic-swap/keep-last-good
behavior `docs/HARNESS_DESIGN.md`'s design section describes; this
cache should follow that *intended* pattern, not claim to extend
already-working code. Invalidation is targeted, not global — a BU-tier
materialization only rebuilds that one BU's index. **The bundled tier
(`skills/`) needs no reload path at all** — it ships with the codebase,
changes only on deploy, load-once-forever. **Staleness here is always
safe**: worst case a genuinely eligible request falls back to
`root_agent` because the cache hasn't caught up — costs LLM spend,
never picks the wrong skill.

**Layer 2 — trust/lifecycle status, `SkillUsageRecord.lifecycle_state`
(`docs/skill_promotion_thresholds.md`).** A freshly materialized skill
starts `lifecycle_state="provisional"`, deliberately *"flagged for more
security-review scrutiny than a stable skill"* until 3 consecutive
successes, and auto-demotes back to review after 5 consecutive
failures. Serving a `"provisional"` or just-demoted skill through the
zero-review deterministic path defeats the entire reason that period
exists. This **must not be coarsely cached** the way Layer 1 is —
staleness here has a correctness cost, not just a performance one: a
demoted skill needs to stop matching on the very next request, not
after some reload lag. Read live at match time instead. Since it's a
single indexed lookup by `skill_id`, not a directory walk, there's
little performance reason to cache it anyway — where it actually
persists is still `docs/remaining_deep_dives.md` item 2's open
storage-backend question, unaffected by this doc either way.

**Corrected filter**:
```python
def resolve_skill_candidates(spec: dict, bu_id: str, org_id: str) -> list[Skill]:
    normalized = {SPEC_TYPE_TO_CFN_TYPE[r["type"]] for r in spec["resources"]}
    for tier_dir in [f"workspaces/{bu_id}/skills", f"orgs/{org_id}/skills", "skills"]:
        frontmatters = tier_index.get(tier_dir)   # Layer 1 — cached, coarse-invalidated
        matching_ids = [
            sid for sid, fm in frontmatters.items()
            if set(fm.metadata.get("resource_types", [])) == normalized
            and get_usage_record(sid).lifecycle_state == "stable"   # Layer 2 — read live
        ]
        if len(matching_ids) == 1:
            return [load_skill_from_dir(f"{tier_dir}/{matching_ids[0]}")]
        if matching_ids:
            return []
    return []
```
A `"provisional"` skill matching on `resource_types` alone is **not**
eligible for the deterministic path — it falls through to `root_agent`,
consistent with Part E rule 1's fail-closed philosophy, just applied to
a dimension Part F0/F0b hadn't checked.

## Part F: Closes the loop on skill authoring/templating
`docs/skill_proposal_execution_and_templating.md` Part C's templating
pass has, until now, only ever specified "replace request-specific
literals with named variables" in the abstract. `parse_declared_variables()`
above needs something concrete to parse, which makes this precise for
the first time: the templating pass must emit variables using the
**toolchain's own real declaration syntax**, not a bespoke placeholder
format:
- Terraform path: a genuine `variables.tf` block (`type`, `validation`,
  `default`) — already the conclusion
  `docs/foundation_blueprint_authoring_coding_agent.md` Part D1 reached
  for a different reason (Terraform's "avoid hardcoded values" own
  convention). This doc adds the reason that conclusion matters
  operationally: it's what `check_structured_match()` needs to be able
  to read deterministically.
- CDK/CloudFormation path — new here, not covered by Part D1's
  Terraform-only finding: a genuine CloudFormation template
  `Parameters:` block (`Type`, `AllowedValues`, `AllowedPattern`,
  `Default`) plays the identical role. Both toolchains this project
  already supports have a native, structured way to declare "what this
  template needs filled in" — the templating pass should use whichever
  one is native to the skill's toolchain, not invent a third schema
  that works the same way for both.

## Open questions / not yet decided
- **Resolved in Part F0**: `resolve_skill_candidates()`'s exact matching
  signal — verified by direct package inspection that `SkillToolset`/
  `SkillRegistry` is LLM-mediated at every layer (an abstract
  `search_skills`, exposed as an agent-callable tool taking a free-text
  query) and therefore cannot be reused for the deterministic path at
  all. A new `SkillProposal.resource_types: list[str]` field (CFN-style,
  matching `infra/allowed-resource-types.json`'s existing convention)
  plus an exact-set match against the request's normalized resource
  types is the actual signal, reusing only the bundled→org→BU tier
  *order*, not `SkillToolset`'s matching mechanism.
- `is_valid_spec_shape()`'s exact schema (required vs. optional
  top-level keys, whether `resources[].type` must match a closed enum)
  — sketched at the concept level, not fully specified.
- Whether `extract_spec_from_free_text()`'s single extraction call
  should itself be retried/self-corrected if its output fails
  `is_valid_spec_shape()` (a bounded retry, same shape as Layer 1) or
  should fail straight to `root_agent` on the first miss — not decided.
- **Resolved in Part F0b**: `load_skills_in_tier()`'s actual mechanism —
  verified as ADK's real `list_skills_in_dir()` (cheap, frontmatter-only,
  non-recursive) plus `load_skill_from_dir()` (one full load, winner
  only). Surfaces a new failure mode (frontmatter-valid, body-invalid —
  fails closed to `root_agent`, not previously covered by Part E).
- **Resolved in Part F0c**: the tier-loading performance concern, plus a
  correctness gap it surfaced along the way — `resolve_skill_candidates()`
  never checked `SkillUsageRecord.lifecycle_state`, so a `"provisional"`
  or just-demoted skill could match deterministically with zero review.
  Two-layer caching policy: `Frontmatter`/`resource_types` cached coarsely
  (reload-triggered by materialization, staleness costs only performance);
  `lifecycle_state` read live, never coarsely cached (staleness there
  costs correctness).

## How this relates to the existing docs
- Resolves `docs/deterministic_plan_drafting.md`'s open question on
  what makes a match "structured enough" — `has_structured_match` is no
  longer a placeholder.
- Designs `envelope_to_spec(envelope)`, referenced but never defined in
  `docs/plan_request_verified_implementation.md` and
  `docs/deterministic_plan_drafting.md`'s own code sketches.
- Extends `docs/skill_proposal_execution_and_templating.md` Part C's
  templating pass with a concrete requirement (toolchain-native variable
  declarations) and a CDK/CloudFormation `Parameters:` block equivalent
  not covered by `docs/foundation_blueprint_authoring_coding_agent.md`
  Part D1's Terraform-only finding.
- Reuses `docs/skills_and_workspace_design.md`'s bundled→org→BU tier
  search unchanged — this doc adds a completeness/ambiguity check on
  top of skill selection, not a replacement for it.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
