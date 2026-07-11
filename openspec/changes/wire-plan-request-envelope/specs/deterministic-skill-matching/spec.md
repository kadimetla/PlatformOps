## ADDED Requirements

### Requirement: `envelope_to_spec` parses structured input deterministically before falling back to an LLM
The system SHALL attempt `yaml.safe_load` against `envelope.raw_payload`
and validate it against the structured spec shape before ever invoking a
model. The system SHALL invoke a single, routing-tier extraction call
only when deterministic parsing fails or the result doesn't match the
expected shape.

#### Scenario: A structured webhook payload never invokes an LLM
- **WHEN** `envelope.raw_payload` is valid YAML matching the structured
  spec shape
- **THEN** `envelope_to_spec` returns the parsed dict directly, with zero
  model calls

#### Scenario: Free-text chat input triggers exactly one extraction call
- **WHEN** `envelope.raw_payload` is not valid YAML or fails the
  structured-shape check
- **THEN** `envelope_to_spec` invokes exactly one routing-tier extraction
  call and returns its structured output, without invoking `root_agent`'s
  full drafting graph

### Requirement: A skill match requires an unambiguous resource-type match at the most specific tier
The system SHALL search skill tiers in order (BU, org, bundled) and
SHALL treat a tier as matched only when exactly one skill's
`resource_types` equals the request's normalized resource-type set.

#### Scenario: Two skills matching at the same tier is not structured
- **WHEN** two or more skills in the most-specific tier with any match
  declare the same `resource_types` set as the request
- **THEN** `check_structured_match` returns `has_structured_match=False`
  and does not fall through to a less-specific tier to break the tie

#### Scenario: A superset or partial resource-type match does not count
- **WHEN** a skill's `resource_types` is a superset of, or only
  partially overlaps, the request's normalized resource types
- **THEN** that skill is not treated as a candidate

### Requirement: A skill match also requires `lifecycle_state == "stable"`, read live
The system SHALL read `SkillUsageRecord.lifecycle_state` for the
matched candidate directly from storage at match time, and SHALL NOT
serve the deterministic path for a skill whose `lifecycle_state` is not
`"stable"`.

#### Scenario: A provisional skill falls back to root_agent despite matching resource_types
- **WHEN** a skill's `resource_types` exactly matches the request but its
  `lifecycle_state` is `"provisional"`
- **THEN** `check_structured_match` returns `has_structured_match=False`

#### Scenario: A skill with no usage record yet is treated as not yet trusted
- **WHEN** no `skill_usage_records` row exists for a matched skill's
  `skill_path`
- **THEN** its `lifecycle_state` is treated as `"provisional"` (fail
  closed), not as trusted by default

### Requirement: Every required template variable resolves from spec, default, or WorkspaceBundle only
The system SHALL treat a skill match as structured only if every
variable declared in the matched skill's `draft_iac_template` resolves
from the request's `spec`, the variable's own declared default, or the
resolved `WorkspaceBundle` — and from no other source.

#### Scenario: A missing required variable with no default blocks the deterministic path
- **WHEN** a matched skill's template declares a required variable with
  no default, and neither `spec` nor `WorkspaceBundle` supplies a value
- **THEN** `check_structured_match` returns `has_structured_match=False`
  with that variable listed in `missing_vars`

### Requirement: A structured match drafts via SkillTemplateFillAgent with zero LLM calls
The system SHALL fill the matched skill's `draft_iac_template` and run
Layer 1 static validation entirely within a deterministic `BaseAgent`
subclass, making no model calls.

#### Scenario: A structured match never invokes an LLM to draft
- **WHEN** `check_structured_match` returns `has_structured_match=True`
- **THEN** `plan_request` constructs `SkillTemplateFillAgent` instead of
  `root_agent`, and the resulting `PlanRecord`'s drafting path makes zero
  calls to any `LlmAgent`

#### Scenario: A Layer 1 validation failure does not silently retry via root_agent
- **WHEN** `SkillTemplateFillAgent`'s bounded static-validation retry
  loop is exhausted without producing a passing draft
- **THEN** the failure is surfaced to the caller as a drafting failure,
  and `plan_request` does NOT silently fall back to invoking `root_agent`
  for the same request
