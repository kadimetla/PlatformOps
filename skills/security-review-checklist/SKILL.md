---
name: security-review-checklist
description: >
  Procedure for reviewing a provisioning plan before it executes against real
  AWS resources, covering both the CDK/CCAPI path and the Terraform path.
  Trigger whenever a provisioning sub-agent proposes a plan that creates or
  modifies infrastructure.
version: 0.2.0
allowed-tools: ""
---

# Security Review Checklist

## When to use this skill
Any time a provisioning plan (a "Vibe Diff") is submitted for approval before
an infrastructure-modifying tool call executes, on either path.

## Checks common to both paths

1. **Check the cost ceiling.** The plan's estimated cost must be at or below
   `MAX_ESTIMATED_MONTHLY_COST_USD`.
2. **Check region.** Reject plans targeting a region outside the one
   configured in `.env` (`AWS_REGION`).
3. **Check resource naming.** Resource names must be prefixed
   `platformops-demo-` so they're identifiable for teardown.
4. **Check for destructive scope.** Reject any plan that deletes or modifies
   a resource it didn't itself create in this session.
5. **Decide: approve or reject**, returning a specific reason either way —
   never approve silently, never reject without saying what to fix.

## Path-specific checks: `cdk` (aws-iac-mcp-server + ccapi-mcp-server)

6. **Check the IAM allow-list.** Every action implied by the plan must
   appear in `infra/iam-policy.json`.
7. **Check the resource-type allow-list.** CCAPI accepts an arbitrary
   CloudFormation-style resource type as a parameter — IAM permissions alone
   don't bound this. Every resource type in the plan must appear in
   `infra/allowed-resource-types.json`. This check is not optional or
   redundant with #6 — see `infra/README.md` for why they're separate.
8. **Confirm validation already ran.** The plan should reference passing
   `validate_cloudformation_template` and
   `check_cloudformation_template_compliance` results. Reject if these
   weren't run.

## Path-specific checks: `terraform` (HashiCorp Terraform MCP Server)

6. **Confirm the target workspace** is the one configured for this project,
   not an arbitrary workspace `TFE_TOKEN` happens to have access to.
9. **Confirm `ENABLE_TF_OPERATIONS=true` was set by the operator**, not
   requested by the agent mid-session — reject if the plan implies this flag
   needs to be turned on to proceed; that's a human decision, not something
   to work around.
10. **Inspect the plan's resource changes** (from `create_run`'s plan
    output) for the same region/naming/destructive-scope concerns as the
    common checks — Terraform's plan diff is your equivalent of the CDK
    path's synthesized template.

## Notes
- This checklist intentionally has no tool calls of its own — it's a pure
  reasoning/gating step evaluated against the Vibe Diff text and the static
  policy files (`infra/iam-policy.json`, `infra/allowed-resource-types.json`).
  Keep it deterministic and auditable: log every approve/reject decision
  with the reason.
- The two paths share the common checks but diverge on how blast radius is
  bounded — CDK/CCAPI via a resource-type allow-list, Terraform via
  workspace scope and an operator-controlled kill switch. Don't assume one
  path's guardrail substitutes for the other's.
