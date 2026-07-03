# PlatformOps Agent

Multi-agent system that does what a platform/infra ops team does: takes a
request (or a structured architecture spec), checks it for SDLC compliance,
provisions the approved AWS infrastructure, and gates every real-world action
behind an explicit security review.

## Problem
Every org running workloads on AWS needs a platform ops function to turn app
requirements into provisioned, secure, compliant infrastructure. That's
typically slow, manual, and ticket-driven, and compliance review lags behind
what's actually deployed.

## Solution (MVP scope)
Given a structured infra spec, this system:
1. Checks it against a versioned reference-architecture spec (`spec/`).
2. If compliant, drafts a provisioning plan and requires explicit approval
   before any AWS-modifying action executes.
3. Provisions a static web app (S3 + CloudFront) via a narrow, purpose-built
   MCP server.

**Out of scope for this MVP** (documented as roadmap, not built): diagram
image upload/parsing (input is a structured YAML spec instead), compute
workloads beyond static hosting, multi-cloud, and a live public deployment.

## Architecture
```
User request / spec
        │
        ▼
platformops_orchestrator (ADK root agent)
        │
        ├── sdlc-diagram-compliance-check skill ──► spec/check_compliance.py
        │        (checked against spec/reference_architecture.md)
        │
        ▼
provisioning_agent ──uses──► provision-static-web-app skill
        │                            │
        │                    produces a "Vibe Diff"
        │                    (plain-English action summary)
        ▼
security_agent ──uses──► security-review-checklist skill
        │        (checks infra/iam-policy.json allow-list + cost ceiling)
        │
        ▼ (approved only)
aws_mcp_server (MCP, stdio) ──boto3──► AWS (S3 + CloudFront)
```

Key design decisions:
- **Skills vs. MCP**: Skills (`skills/`) encode *procedure* (what steps to
  take, what to check); the MCP server (`mcp_server/`) encodes *reach* (the
  actual AWS calls). Skills call MCP tools when they need to touch AWS —
  they don't reimplement AWS access themselves.
- **Security is defense-in-depth**: the security-review-checklist skill gates
  actions before they're attempted, and the MCP server itself re-checks the
  IAM allow-list and cost ceiling before executing — a compromised or
  mis-prompted agent can't bypass the check by skipping the review step.
- **Compliance checking is deterministic**: `spec/check_compliance.py` is a
  plain script, not an LLM call, so results are auditable and reproducible.

## Setup

### 1. Create a dedicated AWS sandbox account
Don't run this against an account with other workloads in it.
1. Create a new AWS account for this project only (via
   [AWS Organizations](https://console.aws.amazon.com/organizations/) if you
   already have a payer account, or a standalone signup otherwise).
2. Sign in to that account's root user once, then stop using the root user
   for anything below — everything else uses a scoped IAM identity.

### 2. Set a billing alarm and budget before creating anything else
1. In the Billing console, enable **"Receive Billing Alerts"**
   (Billing → Billing preferences).
2. Create a CloudWatch billing alarm, e.g. triggered at **$10**:
   ```bash
   aws cloudwatch put-metric-alarm \
     --alarm-name platformops-demo-billing-alarm \
     --metric-name EstimatedCharges --namespace AWS/Billing \
     --statistic Maximum --period 21600 --threshold 10 \
     --comparison-operator GreaterThanThreshold --evaluation-periods 1 \
     --dimensions Name=Currency,Value=USD \
     --region us-east-1
   ```
   (Billing metrics are only published in `us-east-1`, regardless of which
   region you provision resources in.)
3. Create an AWS Budget with an alert threshold as a second layer:
   ```bash
   aws budgets create-budget \
     --account-id <YOUR_ACCOUNT_ID> \
     --budget file://infra/budget.json \
     --notifications-with-subscribers file://infra/budget-notification.json
   ```
   (Create `infra/budget.json` / `infra/budget-notification.json` from the
   [AWS Budgets CLI examples](https://docs.aws.amazon.com/cli/latest/reference/budgets/create-budget.html)
   if you want this automated; the console UI is faster for a one-off demo.)

### 3. Create a scoped IAM user for the agent
Never use root credentials or an admin user for the agent.
```bash
aws iam create-user --user-name platformops-agent
aws iam put-user-policy \
  --user-name platformops-agent \
  --policy-name platformops-demo-allowlist \
  --policy-document file://infra/iam-policy.json
aws iam create-access-key --user-name platformops-agent
```
Save the `AccessKeyId` / `SecretAccessKey` from the last command — this is
the only place they're shown. See `infra/README.md` for the policy's
caveats (tag-condition limitations) before relying on it as your only
safeguard; the MCP server's own allow-list check is the second layer.

### 4. Configure AWS credentials locally
```bash
aws configure --profile platformops-sandbox
# AWS Access Key ID / Secret Access Key: from step 3
# Default region: us-east-1 (or your chosen region)
```
Verify it resolves to the scoped user, not your personal credentials:
```bash
aws sts get-caller-identity --profile platformops-sandbox
# arn should be arn:aws:iam::<ACCOUNT_ID>:user/platformops-agent
```

### 5. Configure the project
```bash
uv sync   # or: pip install -e .
cp .env.example .env
```
Edit `.env`:
```
AWS_PROFILE=platformops-sandbox
AWS_REGION=us-east-1
GOOGLE_API_KEY=<your Google AI Studio key>
MAX_ESTIMATED_MONTHLY_COST_USD=5
```

### 6. Sanity-check before touching AWS
Run the deterministic compliance check first — it makes no AWS calls:
```bash
python spec/check_compliance.py spec/example_submission.yaml
```
Confirm it prints `PASS`. Then try a spec that should fail (e.g., copy
`spec/example_submission.yaml`, set `public_write: true` on the bucket) and
confirm it prints `FAIL` with the right reason — this is your evidence the
guardrail actually works, worth capturing for the demo video.

### 7. Run the agent
```bash
export $(cat .env | xargs)   # or use direnv / your preferred env loader
python -m agents.orchestrator
```
Watch for the plain-English action summary before anything is created —
if the agent tries to skip straight to `create_static_site` without it,
stop and check the `provision-static-web-app` and `security-review-checklist`
skill instructions before proceeding.

### 8. Tear down immediately after recording the demo
```bash
./scripts/teardown.sh
```
Then manually confirm in the AWS console that the S3 bucket and CloudFront
distribution are gone (CloudFront deletion requires the distribution to
finish disabling first — the script prints a reminder to re-run for this).
Finally, check the Billing console once more before walking away.

## Project layout
- `agents/` — ADK orchestrator + Provisioning and Security sub-agents
- `skills/` — Agent Skills (procedure, not AWS access)
- `mcp_server/` — MCP server exposing the actual AWS actions
- `spec/` — reference architecture (BDD-style rules) + compliance checker
- `infra/` — IAM allow-list policy for the agent's AWS credentials
- `scripts/` — teardown script for demo cleanup

## Security note
No API keys or credentials are committed. `.env` is gitignored; use
`.env.example` as the template. AWS credentials should be scoped to the
policy in `infra/iam-policy.json` and used only against a disposable sandbox
account.
