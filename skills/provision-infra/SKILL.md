---
name: provision-infra
description: >
  Procedure for provisioning AWS infrastructure from a structured spec, using
  either AWS CDK-native tooling or Terraform depending on the user's stated
  preference. Trigger when the user asks to deploy, host, or provision
  infrastructure on AWS and states or implies a tool preference.
version: 0.2.0
allowed-tools: >-
  mcp__aws_iac__read_iac_documentation_page
  mcp__aws_iac__validate_cloudformation_template
  mcp__aws_iac__check_cloudformation_template_compliance
  mcp__ccapi__create_resource
  mcp__ccapi__get_resource
  mcp__ccapi__update_resource
  mcp__ccapi__delete_resource
  mcp__ccapi__list_resources
  mcp__terraform__search_providers
  mcp__terraform__create_run
  mcp__terraform__action_run
---

# Provision Infrastructure (multi-tool)

## When to use this skill
The user's request describes provisioning AWS infrastructure and states (or
you should ask for) which IaC tool they prefer: **CDK-native** or
**Terraform**. This skill generalizes the earlier static-site-only procedure
to route to the right toolchain.

## Step 0: Determine the tool preference
Ask, or infer from context, whether the user wants:
- `cdk` — AWS-native, no external account beyond AWS credentials
- `terraform` — requires an HCP Terraform account and `TFE_TOKEN` (see
  README.md setup); state is managed remotely, not locally

If the user has no preference, default to `cdk` — it has one fewer external
dependency (no HCP Terraform account needed).

## Path A: `cdk` (AWS-native via aws-iac-mcp-server + ccapi-mcp-server)

`aws-iac-mcp-server` and `ccapi-mcp-server` are two separate, complementary
tools — neither alone provisions infrastructure end to end:

1. **Draft the CDK app / CloudFormation template** for the requested
   resources. Use `search_cdk_documentation` / `search_cdk_samples_and_constructs`
   (from `aws-iac-mcp-server`) for patterns; this server is read-only —
   docs, linting, compliance checks — it does not deploy anything.
2. **Validate before touching AWS**: run `validate_cloudformation_template`
   (cfn-lint) and `check_cloudformation_template_compliance` (cfn-guard) on
   the synthesized template. Do not proceed past a failing validation.
3. **Produce the plain-English "Vibe Diff"** summary of exactly which
   resource types will be created/updated/deleted via Cloud Control API,
   and the estimated cost — this is what `security_agent` reviews.
4. **Wait for `security_agent` approval.**
5. **Execute via `ccapi-mcp-server`**: `create_resource` (or `update_resource`
   / `delete_resource`) per resource, using the resource-type identifiers
   from the validated template. CCAPI auto-tags resources with `MANAGED_BY`
   — confirm the tags match `platformops-demo-*` naming so teardown can find
   them.
6. **Verify with `get_resource` / `list_resources`** and report the result.

**Important distinction to be explicit about**: this path does not literally
run `cdk deploy`. It uses CDK documentation/validation tooling to *design*
the change and AWS's Cloud Control API to *apply* it — a legitimate,
AWS-native execution path, not a shortcut to hide.

## Path B: `terraform` (via HashiCorp's official Terraform MCP Server)

1. **Confirm `TFE_TOKEN` is configured** (HCP Terraform account required —
   see README.md). If missing, tell the user this path needs that setup and
   offer the `cdk` path instead.
2. **Search the registry** (`search_providers` / module docs) to draft the
   Terraform configuration for the requested resources.
3. **Produce the plain-English "Vibe Diff"** summary before creating any
   run — same requirement as Path A.
4. **Wait for `security_agent` approval.**
5. **Create the run** via `create_run` against the configured HCP Terraform
   workspace, then `action_run` to apply — only if
   `ENABLE_TF_OPERATIONS=true` is set (it is deliberately off by default;
   turning it on is itself a security-relevant decision the operator makes,
   not the agent).
6. **Report the run status and outputs** back to the user.

## Notes
- Both paths share the same review/approval gate — the *how* of execution
  differs, the *whether it's allowed to execute* logic does not.
- GCP and Azure are not implemented in this skill yet — see README.md's
  roadmap section for the specific MCP servers to integrate next
  (Google-managed MCP servers / GCE MCP server; Azure MCP Server 2.0 /
  Azure Resource Manager MCP Server).
