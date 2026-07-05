# End-to-End Flow: A Worked Example (CopilotKit → Skill Registry → Execution)

## Status
Synthesis, not a build log. This ties together
`docs/ui_and_multitenancy_deep_dive.md` (the CopilotKit/AG-UI/A2UI channel
and Org→BU→team-member resolution) and
`docs/skills_and_workspace_design.md` (the bundled→org→BU skill
precedence and skill-authoring gate) into one concrete, ordered walkthrough.
It doesn't introduce new decisions — see those two docs, plus
`docs/HARNESS_DESIGN.md` and `docs/current_architecture.md`, for the
reasoning behind each step. Read this one when you want the *whole* path
in one place instead of assembled from three documents.

## The example
Alice (`channel_user_id="alice@acme.com"`), a member of Acme's Payments
BU, opens the CopilotKit UI and types: *"Set up a PCI-compliant S3 bucket
with encryption for storing transaction logs."*

## 1. CopilotKit UI → Gateway (identity resolution)
Alice authenticates via org SSO. This is a real difference from
Slack/webhook channels, worth stating plainly: **a UI channel resolves
identity via the login session, not via a binding-table lookup.**
Slack/webhook infer org/BU from *which channel account* sent the message
(`config/bindings.yaml`); CopilotKit already knows *who Alice is* the
moment she logs in. Her session already carries `org_id="acme"`,
`bu_id="payments"`.

AG-UI transport streams her message to the Gateway's `copilotkit` channel
adapter, which builds:
```python
RequestEnvelope(
    org_id="acme",
    bu_id="payments",
    channel="copilotkit",
    channel_user_id="alice@acme.com",
    raw_payload="Set up a PCI-compliant S3 bucket with encryption for storing transaction logs.",
)
```

## 2. Gateway loads the BU's workspace
`workspaces/acme-payments/` — credentials, `allowed_resource_types`,
`cost_ceiling_usd`, and the `members` list (see
`docs/skills_and_workspace_design.md`'s `TeamMember` sketch) confirms
Alice is a valid requester in this BU, and what her role is (requester,
approver, admin).

## 3. Skill registry resolution — bundled → org → BU
The Gateway checks for a matching skill in precedence order (see
`docs/skills_and_workspace_design.md` Part B for the full design):

1. **`workspaces/acme-payments/skills/`** first — maybe Payments already
   has a `pci-compliant-storage` skill from an earlier, approved
   `SkillProposal`. PCI-DSS is Payments-specific, so this is exactly
   where it should live, not at org or global level.
2. If nothing matches, **`orgs/acme/skills/`** — maybe there's a general
   "encrypted-storage" skill (an Acme-wide encryption/tagging standard)
   that's close but not PCI-specific.
3. If nothing matches there either, fall through to
   **bundled/global `skills/provision-infra/SKILL.md`** — the generic
   CDK/Terraform routing skill that exists today.

## 4. Branch: reuse an existing pattern vs. author a new one
- **BU-level skill matched**: the provisioning agent starts from that
  skill's *already-reviewed* IaC pattern, filling in request-specific
  parameters (bucket name, tags) rather than drafting from nothing.
  Faster, and it's been through security review before — the common case
  as the skill library grows over time.
- **Nothing matched**: the CDK/Terraform specialist drafts a genuinely
  new template from scratch — today's flow, unchanged. This is also the
  moment a fresh `SkillProposal` *could* be created, scoped to Payments
  only (see `docs/skills_and_workspace_design.md` Part C for why it's
  never auto-promoted beyond the originating BU).

## 5. Deterministic preflight
`spec/check_compliance.py` runs against whichever template resulted —
identical whether the pattern was reused or freshly drafted.

## 6. Security review — provenance should inform scrutiny
`security_agent` reviews the Vibe Diff. A request built on a
previously-approved BU skill is lower-risk (already vetted); a brand-new,
never-before-seen pattern deserves more scrutiny — likely mandatory human
approval rather than agent-only. This is the risk-tier Control UI concept
already named in `docs/HARNESS_DESIGN.md`, applied concretely here based
on skill provenance (bundled vs. org vs. BU vs. freshly-drafted).

## 7. Two separate approval tracks, not one
- **Approving *this* infra change** (the `PlanRecord`/`ToolIntent`) —
  checked against Alice's `WorkspaceBundle`, requiring
  `TeamMember.role="approver"` if human sign-off is required.
- **Separately, optionally, approving *persisting* the new pattern as a
  reusable `SkillProposal`** — a reviewer could approve executing the
  change now without approving it as a future template ("go ahead and
  create this bucket, but don't save this as a pattern yet, I want to
  refine it"). These are independent decisions with independent approval
  records.

## 8. Dispatcher gate
`harness/tool_dispatcher.py`'s `BrokeredToolDispatcher.evaluate_intent()`
— deny-by-default: approval matches, resource type allow-listed, region
matches, cost under ceiling. Unchanged from the core design; this part is
real, tested code today (see `tests/test_harness.py`), just not yet wired
to a live request.

## 9. Execution
Only now does the real CCAPI (or Terraform) call happen.

## 10. Response rendered back in the same UI
An A2UI success/failure card streams back over AG-UI to Alice's
CopilotKit session — an interactive component, not a text blob.

## 11. Audit
`org_id`, `bu_id`, `channel_user_id` (once that gap is fixed — see
`docs/ui_and_multitenancy_deep_dive.md`), which skill tier was used
(bundled/org/BU, plus version if a stored skill), the decision, and the
reason all get written to the audit log.

## What's real code today vs. design only
| Step | Status |
|---|---|
| 1 (CopilotKit channel, identity via SSO) | Design only |
| 2 (workspace bundle loading) | Real, tested — `harness/config_engine.py` |
| 3 (skill registry, bundled→org→BU resolution) | Design only |
| 4 (reuse vs. author branch, `SkillProposal`) | Design only |
| 5 (deterministic preflight) | Real code (`spec/check_compliance.py`), not yet called automatically |
| 6 (security review) | Real LLM reasoning step, prompt-level only — see `docs/current_architecture.md` Section 5 |
| 7 (two-track approval) | Design only |
| 8 (dispatcher gate) | Real, tested in isolation — `harness/tool_dispatcher.py` |
| 9 (execution) | Real MCP tools exist; not yet gated by step 8 in the live agent graph |
| 10 (A2UI response rendering) | Design only |
| 11 (audit, minus `channel_user_id`) | Partially real — the SQLite write is tested, the missing field is a tracked gap |

The one required next step to make any of this real end to end is still
`docs/planned_implementation.md` Phase 3 — everything in this document is
additional design layered on top of that, not a replacement for it.
