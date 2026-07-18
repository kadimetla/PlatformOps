---
last_updated: 2026-07-17
owner: platformops-agent maintainers
scope: a three-part frame for every workflow's data model -- what's allowed in, how it gets processed, what shape/trust-level the result carries -- and where each leg is real, designed, or missing today. Extends docs/creation_profiles_and_deterministic_discovery.md and docs/infra_discovery_and_platform_app_split.md
reviewed_by: unreviewed (first draft)
---

# Input, Purposing, and Output Profiles

## Status
Design only for the parts that are new (Part C, the output-profile
sketch). The other two legs aren't new concepts — this doc is mostly
naming and connecting things that already exist, plus finding the one
place they're asymmetric. Grounded against real schema code
(`gateway/schemas.py`), not assumption.

## Part A: The frame
Every workflow this project has (or will) build takes something in,
does something to it, and produces something out. Naming each stage's
governing "profile" gives all three a consistent, reusable shape:

| Profile | Governs | Question it answers |
|---|---|---|
| **Input** | What's allowed to enter | "Is this request even valid for this BU?" |
| **Purposing** | How it gets processed | "What mechanism produced this result, and how would we verify it later?" |
| **Output** | What shape/trust-level the result carries | "What kind of thing came out, and how much should it be trusted?" |

## Part B: Mapped against real code

| Profile | `workflows/drafting/` | `workflows/inquiry/` |
|---|---|---|
| Input | `WorkspaceBundle` (`allowed_resource_types`, `cost_ceiling_usd`, `aws_region`) + `run_compliance_preflight()` — both real, built | `InquiryQuery` + `WorkspaceBundle.allowed_resource_types` (bounds `classify_resource_type`'s candidates) — real, built |
| Purposing | `CreationProfile` (skill_path, toolchain, iac_source) — designed, `docs/creation_profiles_and_deterministic_discovery.md`, not yet stamped anywhere | `classify_resource_type`'s resolution (given directly vs. classified via `select_resource_type`) — real, built, though not currently exposed as a named "profile" object |
| Output | **Nothing** — `PlanRecord`/`ToolIntent` carry no classification field at all | `InquiryResult.record.resource_category`/`.layer`, once `InfraInventoryRecord` is populated — real fields, but only reachable through the record, not on `InquiryResult` itself |

Input and purposing aren't new — this doc's contribution is mostly
naming them as one consistent triple. **Output is the genuinely
underdesigned leg**, and it's asymmetric in a specific way worth
stating precisely: `InfraInventoryRecord` already carries two
output-profile-shaped fields (`resource_category`: network/compute/
identity/storage; `layer`: foundation/app) — but only once something
writes an inventory row. `workflows/drafting/`'s own output objects
(`PlanRecord`, `ToolIntent`) carry neither, at the moment they're
actually produced, before any inventory write happens.

## Part C: Sketch — what a real output profile could look like
Not a new vocabulary invention where one isn't needed — `resource_category`
and `layer` already exist and should be reused, not reinvented, for
drafting's output the same way they'd apply to inquiry's:

```python
class OutputProfile(BaseModel):
    resource_category: Optional[str] = None  # reuses classify_resource_category()
    layer: Optional[str] = None              # "foundation" | "app" | None
    confidence: Optional[str] = None         # NEW -- see below
```

`layer` in particular already has a real anchor beyond `InfraInventoryRecord`:
`docs/infra_discovery_and_platform_app_split.md` Part A sketches
`infra/allowed-resource-types.json` splitting into
`{"type": "AWS::S3::Bucket", "tier": "app"}`-shaped entries — the same
foundation/app distinction, resource-type-scoped, on the *input* side.
An output profile's `layer` would be the same classification applied to
what was actually produced, not what was allowed.

`confidence` is the one genuinely new field, generalizing a pattern
`InquiryResult` already has informally: `found` + `clarifying_question`
together already distinguish "confirmed" from "needs clarification."
Naming that as an explicit `confidence` field (`"confirmed"` |
`"unconfirmed"` | `"needs_clarification"`) would let `PlanRecord` carry
the same distinction drafting currently has no way to express — e.g., a
deterministic skill-fill draft is `"confirmed"` (matched exactly,
zero LLM judgment), while an LLM-drafted plan from the general graph
path might warrant `"unconfirmed"` until human/security review, a
distinction currently invisible in `PlanRecord`'s shape.

## Part D: `lifecycle_state` is adjacent, not the same thing
Closing `docs/skill_loading_and_enforcement_gap.md` Finding 4 surfaced
this distinction concretely. Skill `lifecycle_state`
(`"provisional"`/`"stable"`, `gateway/skill_usage_store.py`) looks like
it could be an output profile field, but it isn't one — it's an
**aggregate** signal ("has this purposing profile's output been
trustworthy across many past requests"), not a **per-result** one. A
single request's `PlanRecord` doesn't have its own `lifecycle_state`;
it inherits whatever the matched skill's current aggregate state is at
that moment. An output profile, by contrast, would describe *this one
result* — closer to `confidence` above than to `lifecycle_state`. Worth
keeping distinct: conflating "is this specific result trustworthy" with
"has this mechanism been trustworthy historically" would hide the exact
kind of new-pattern-poisoning risk `docs/skills_and_workspace_design.md`
Part C already named for skill authoring.

## Real vs. designed
| Piece | Status |
|---|---|
| `WorkspaceBundle`, `run_compliance_preflight()` (input) | Real, built |
| `InquiryQuery`, `classify_resource_type` (input/purposing) | Real, built |
| `CreationProfile` (purposing) | Designed only (`docs/creation_profiles_and_deterministic_discovery.md`) |
| `InfraInventoryRecord.resource_category`/`.layer` (output, inquiry-side) | Real fields, populated only once a sweep/hook writes a row |
| `OutputProfile` on `PlanRecord`/`ToolIntent` (output, drafting-side) | Not designed anywhere before this doc |
| `infra/allowed-resource-types.json`'s `tier`-per-type split | Designed only (`docs/infra_discovery_and_platform_app_split.md` Part A) |

## Open Questions
- Whether `OutputProfile` should be its own reusable model (attached to
  both `PlanRecord` and `InquiryResult`) or whether each workflow's
  output type just grows its own fields independently — not decided;
  a shared model matches this project's general "reuse the pattern,
  don't reinvent per workflow" discipline, but the two outputs
  (mutating plan vs. read-only lookup) may not need identical shapes.
- `confidence`'s exact vocabulary — sketched with three values above,
  not verified against every workflow's actual output shapes yet
  (`workflows/audit/` doesn't exist to check against).
- Whether `layer` should be resolved at drafting time (from
  `infra/allowed-resource-types.json`'s proposed `tier` field, once that
  exists) or only after a real inventory row exists — affects whether a
  `PlanRecord`'s `OutputProfile` is available immediately or only after
  dispatch succeeds.

## How this relates to the existing docs
- Extends `docs/creation_profiles_and_deterministic_discovery.md` —
  that doc's `CreationProfile` is this doc's "purposing" leg by another
  name; not redefined here, just placed in the larger three-part frame.
- Extends `docs/infra_discovery_and_platform_app_split.md` Part A —
  reuses its proposed `tier`-per-type split as the natural source for
  an output profile's `layer` field, rather than inventing a separate
  classification.
- Connects to, but explicitly distinguishes itself from,
  `docs/skill_loading_and_enforcement_gap.md`'s `lifecycle_state`
  (Part D above) — aggregate trust over time vs. per-result
  classification are different things that happen to look similar.
- Doesn't change any built code — `InfraInventoryRecord`'s existing
  fields are reused, not modified; `PlanRecord`/`ToolIntent` are
  unchanged until `OutputProfile` moves from sketch to design.
