# Reference Architecture Spec — Static Web App

This is the source of truth for what a compliant deployment looks like,
following the course's spec-driven development pattern: the spec is durable
and version-controlled; the diagram/IaC submitted by a user is checked
*against* it, not the other way around.

Scenarios are written Given/When/Then so `spec/check_compliance.py` (or an
agent) can evaluate them mechanically against a submitted spec (see
`spec/example_submission.yaml` for the input shape).

This file checks a submitted resource spec's *content*. For specs
covering the harness *pipeline stages* a request moves through (intake,
binding resolution, dispatch, etc.), see `spec/flow_steps/` — a separate,
complementary layer; see `docs/flow_step_spec_decomposition.md` for why
they're kept apart.

## Scenario: No public write access
```
Given a submitted infrastructure spec
When any S3 bucket in the spec has public write permissions
Then compliance check FAILS with reason "public write access is prohibited"
```

## Scenario: Resource naming convention
```
Given a submitted infrastructure spec
When any resource name does not start with the environment prefix
  (e.g. "platformops-demo-" for this sandbox)
Then compliance check FAILS with reason "resource name violates naming convention"
```

## Scenario: Region restriction
```
Given a submitted infrastructure spec
When any resource targets a region other than the approved region
  (AWS_REGION from .env)
Then compliance check FAILS with reason "resource targets a non-approved region"
```

## Scenario: HTTPS enforced
```
Given a submitted infrastructure spec
When a CloudFront distribution's ViewerProtocolPolicy is not
  "redirect-to-https" or "https-only"
Then compliance check FAILS with reason "viewer traffic is not forced to HTTPS"
```

## Scenario: Cost ceiling respected
```
Given a submitted infrastructure spec
When the estimated monthly cost exceeds MAX_ESTIMATED_MONTHLY_COST_USD
Then compliance check FAILS with reason "spec exceeds approved cost ceiling"
```

## Scenario: Compliant spec passes
```
Given a submitted infrastructure spec
When all of the above conditions are satisfied
Then compliance check PASSES
```

## Notes
This MVP evaluates a **structured YAML spec**, not an uploaded diagram image.
Diagram-image parsing (vision model → structured spec → same compliance
check) is the natural next step and is called out as roadmap in the writeup,
not implemented here.
