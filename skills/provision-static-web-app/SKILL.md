---
name: provision-static-web-app
description: >
  Procedure for provisioning a static web app on AWS (S3 + CloudFront) from a
  structured infra spec. Trigger when the user asks to deploy, host, or
  provision a static site / simple web app on AWS.
version: 0.1.0
allowed-tools:
  - mcp__aws_platformops__estimate_cost
  - mcp__aws_platformops__create_static_site
  - mcp__aws_platformops__get_deployment_status
---

# Provision Static Web App

## When to use this skill
The user's request describes deploying a static or simple client-rendered web
app (no server-side compute) to AWS, either from a plain-language description
or a structured spec (see `spec/reference_architecture.md` for the compliance
rules the result must satisfy).

## Procedure

1. **Parse the request into a structured spec** — app name, region, whether a
   custom domain is needed, expected traffic tier (used for cost estimate).
2. **Call `estimate_cost`** with the draft spec. If the estimate exceeds
   `MAX_ESTIMATED_MONTHLY_COST_USD`, stop and report the estimate to the user
   instead of proceeding.
3. **Produce a plain-English summary** ("Vibe Diff") of exactly what will be
   created: bucket name, CloudFront distribution, region, estimated cost. This
   summary is what `security_agent` reviews — do not skip it or bundle it with
   the tool call.
4. **Wait for `security_agent` approval.** Only after approval, call
   `create_static_site` with the finalized spec.
5. **Call `get_deployment_status`** and report the resulting URL, or the
   failure reason, back to the user.
6. **Never retry a rejected plan automatically** — surface the rejection
   reason and ask the user how to adjust the spec.

## Notes
- This skill only covers the static-site path. Anything requiring compute
  (Lambda, ECS, EC2) is out of scope for this MVP — say so explicitly rather
  than improvising a broader deployment.
