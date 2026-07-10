---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: coding-agent question for foundation-layer blueprint authoring — resolves docs/remaining_deep_dives.md item 11
reviewed_by: unreviewed (first draft)
---

# Coding Agents for the Foundation-Layer Blueprint

## Status
Design + research. Resolves `docs/remaining_deep_dives.md` item 11.
The answer converges on the same conclusion already reached for
Crossplane (`docs/crossplane_comparison_and_pattern_reuse.md`) —
confirmed here for a second, different category of tool, not assumed
by analogy.

## Part A: Open-source coding agents are built for autonomous execution, not "propose and wait"
Researched three real, current tools:
- **OpenHands**: *"iteratively edit files, execute shell commands, and
  browse the Web inside sandboxed containers"* — real execution,
  containerized but autonomous.
- **SWE-agent**: its "Agent-Computer Interface" exposes *"editor, shell
  and test runners as structured actions"* — a more constrained tool
  surface than OpenHands, still direct execution.
- **Aider**: *"edits files directly, and auto-commits changes to
  git"* — no approval gate at all by default.

None has a built-in "draft only, never execute" mode. This is the same
tension already found for Crossplane: a mature tool's core value
(autonomous iterative execution) conflicts directly with this
project's core value (nothing executes without passing
`BrokeredToolDispatcher.evaluate_intent()`).

## Part B: The real distinction is instantiation vs. authoring, not "which coding agent"
Grounded against Terraform's actual standard module structure:
`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `README.md`,
with complex modules further split into `network.tf`/`instances.tf`/
`loadbalancer.tf`-style files. This maps directly onto
`docs/foundation_layer_decomposition.md`'s network/compute/identity
split — a properly authored foundation module genuinely is multi-file.

Two different tasks hide under "create the blueprint":
- **Instantiating an existing module** (the common case — a BU
  consuming `acme/landing-zone/aws`, per
  `docs/foundation_discovery_and_creation_chat_walkthrough.md`'s worked
  example) is a **single-artifact** task. The existing ADK-agent-with-
  retry-loop approach (`docs/three_layer_validation_model.md` Layer 1)
  is already sufficient — no genuine multi-file repository problem to
  solve.
- **Authoring a brand-new reusable module from scratch** (rare — only
  needed once per org, when no shared landing-zone module exists yet)
  *is* a genuine multi-file, repository-shaped task — the kind of work
  OpenHands/SWE-agent/Aider are actually built for.

## Part C: The constraint — borrow the reasoning, refuse the execution
For the common case (instantiation), no new tool is needed. For the
rare case (authoring a new module), a coding-agent-style approach adds
real value **only if its execution model is constrained the same way
everything else in this design already is**: borrow the multi-file
iterative-editing capability, refuse the autonomous shell/file/git-
commit access. Concretely:
- Its output becomes a proposed multi-file diff, not applied files.
- Validated through the same Layer 1 retry loop
  (`docs/three_layer_validation_model.md`) as any other drafted script.
- Applied only by the harness's own dispatcher, never by the coding
  agent itself running in its own sandbox with its own credentials —
  the same "propose, never execute" boundary already enforced for the
  ADK provisioning agents (`docs/planned_implementation.md` Phase 3).

This is the same "borrow the pattern, refuse the runtime" principle
already applied to Crossplane, now stated as a general rule for *any*
externally-sourced coding-agent tool this project might consider, not
just the ones evaluated so far.

## Part D: Two connections this research surfaces

### D1. Templating is Terraform's own variable convention, not a bespoke mechanism
`docs/skill_proposal_execution_and_templating.md` Part C left the
templating mechanism (`draft_iac_template` vs. `draft_iac_snippet`)
undesigned — agent-performed diffing vs. human-marking, unresolved.
Terraform's own standard practice removes the question: *"avoid
hardcoded values in modules, pass them as input variables instead."* A
properly authored module already declares its request-specific values
(names, regions, sizes) as `variables.tf` inputs, not as hardcoded
literals. **Correction to the original design**: `draft_iac_template`
isn't something extracted *after* drafting — it's what a correctly
authored module looks like from the start. `draft_iac_snippet` (the
literal, as-executed artifact) is then *derived* — the module plus this
specific request's variable values (a `terraform.tfvars`-shaped input),
not the other way around. The templating problem dissolves into "did
the agent follow Terraform's own convention," not a new algorithm to
design.

### D2. The dependency chain should correspond to real module wiring
`docs/foundation_layer_decomposition.md`'s `depends_on_foundation_id`
chain (network → compute → identity) is currently a harness-level
bookkeeping record, separate from the actual IaC. Terraform's own
module composition — *"for every resource... include at least one
output... variables and outputs let you infer dependencies between
modules"* — is the native mechanism for exactly this relationship (a
compute module reading `module.network.vpc_id` as an input). **These
should correspond 1:1**, not exist as two parallel dependency
representations: when the toolchain is Terraform,
`depends_on_foundation_id` on a `FoundationRecord` should be
verifiable by checking that the corresponding module's inputs actually
reference the depended-on module's outputs, not just recorded as an
independent harness-side claim.

## Open questions / not yet decided
- Whether authoring a brand-new org-level module should require its
  own, stricter review gate (parallel to foundation-tier's mandatory
  human approval) given it becomes the template every future BU
  instantiation inherits from — not designed, plausibly yes.
- Whether any specific open-source coding agent (OpenHands, SWE-agent,
  Aider, or another) is actually worth integrating in constrained form,
  versus extending the existing ADK agent's own multi-file capability
  (ADK agents can already read/write multiple files via tool calls;
  whether that's sufficient for module-authoring specifically, or
  whether a dedicated tool's repository-aware editing is meaningfully
  better, wasn't evaluated head-to-head) — not decided.
- D2's "verify module wiring matches the recorded dependency chain"
  check — sketched as a principle, no concrete verification mechanism
  designed.

## How this relates to the existing docs
- Resolves `docs/remaining_deep_dives.md` item 11.
- Confirms `docs/crossplane_comparison_and_pattern_reuse.md`'s "borrow
  the pattern, refuse the runtime" principle generalizes beyond
  Crossplane specifically — restated here as a rule for any externally-
  sourced coding-agent tool.
- Corrects `docs/skill_proposal_execution_and_templating.md` Part C's
  open templating-mechanism question.
- Extends `docs/foundation_layer_decomposition.md`'s
  `depends_on_foundation_id` with a concrete correspondence to real
  Terraform module wiring.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [OpenHands vs SWE-agent (2026) — CodeSOTA](https://www.codesota.com/agentic/openhands-vs-swe-agent)
- [Devin vs OpenHands vs SWE-agent: Top AI Coding Agents — Toolhalla](https://toolhalla.ai/blog/devin-vs-openhands-vs-swe-agent-2026)
- [Standard Module Structure — Terraform docs, HashiCorp Developer](https://developer.hashicorp.com/terraform/language/modules/develop/structure)
- [Best practices for reusable modules — Terraform on Google Cloud docs](https://docs.cloud.google.com/docs/terraform/best-practices/reusable-modules)
