# PlatformOps Agent

Multi-agent system that does what a platform/infra ops team does: takes a
request (or a structured architecture spec), checks it for SDLC compliance,
provisions the approved AWS infrastructure, and gates every real-world action
behind an explicit security review.

This repo is a working slice of a larger intended product — a multi-channel,
multi-tenant harness any team could configure for their own cloud/tool needs,
in the spirit of [OpenClaw](https://docs.openclaw.ai/)'s gateway pattern. See
`docs/HARNESS_DESIGN.md` for that design and exactly which parts of it exist
today versus which are designed for later.

## Problem
Every org running workloads on AWS needs a platform ops function to turn app
requirements into provisioned, secure, compliant infrastructure. That's
typically slow, manual, and ticket-driven, and compliance review lags behind
what's actually deployed.

## Solution (MVP scope)
Given a structured infra spec, this system:
1. Checks it against a versioned reference-architecture spec (`spec/`).
2. If compliant, drafts a provisioning plan and requires explicit approval
   before any infrastructure-modifying action executes.
3. Provisions the requested AWS infrastructure via the user's preferred
   toolchain — **CDK-native** (AWS Cloud Control API) or **Terraform**
   (HCP Terraform) — by routing to existing, officially maintained MCP
   servers rather than hand-rolled provisioning code.

**Out of scope for this MVP** (documented as roadmap, not built): diagram
image upload/parsing (input is a structured YAML spec instead), compute
workloads beyond static hosting, GCP/Azure, and a live public deployment.

## Architecture
```
User request / spec
        │
        ▼
platformops_orchestrator (ADK root agent)
        │
        ├── sdlc-diagram-compliance-check skill ──► spec/check_compliance.py
        │        (checked against spec/reference_architecture.md)
        ▼
provisioning_agent (router) ──uses──► provision-infra skill, Step 0
        │        (picks a path by user's stated tool preference)
        │
        ├──► cdk_provisioning_agent ──► aws-iac-mcp-server (design/validate)
        │                          └─► ccapi-mcp-server (execute via
        │                              AWS Cloud Control API)
        │
        └──► terraform_provisioning_agent ──► HashiCorp Terraform MCP Server
                                          (create_run / action_run against
                                           HCP Terraform)
        │
        │        each path produces a "Vibe Diff"
        │        (plain-English action summary) before executing
        ▼
security_agent ──uses──► security-review-checklist skill
        │   (checks infra/iam-policy.json + infra/allowed-resource-types.json
        │    on the CDK path; workspace scope + ENABLE_TF_OPERATIONS on the
        │    Terraform path; cost ceiling and region on both)
        ▼ (approved only)
   AWS (S3 + CloudFront, for this MVP's demo scope)
```

Key design decisions:
- **Skills vs. MCP**: Skills (`skills/`) encode *procedure* (what steps to
  take, what to check, which toolchain to pick); MCP servers encode *reach*
  (the actual cloud API calls). Skills call MCP tools when they need to
  touch a cloud — they don't reimplement cloud access themselves.
- **Route to existing tools, don't rebuild them**: rather than writing our
  own AWS provisioning code, `provision-infra` routes to AWS Labs'
  `aws-iac-mcp-server` + `ccapi-mcp-server` (CDK-native path) or HashiCorp's
  official Terraform MCP Server (Terraform path) — see `README.md`'s
  Roadmap section for why each was chosen over its alternatives.
- **Security is defense-in-depth, and path-aware**: the
  security-review-checklist skill gates actions before they're attempted.
  Because CCAPI's tool interface accepts an arbitrary resource-type
  parameter, IAM permissions alone don't bound blast radius on that path —
  `infra/allowed-resource-types.json` is a second, application-level
  allow-list the security agent checks explicitly. The Terraform path is
  scoped differently: by HCP Terraform workspace access and an
  operator-controlled `ENABLE_TF_OPERATIONS` flag the agent cannot toggle
  itself. See `infra/README.md` for the full breakdown.
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
caveats (tag-condition limitations, and why there's a *separate*
`infra/allowed-resource-types.json` for the CDK path) before relying on IAM
alone as your safeguard.

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

### 5. Install `uv` and confirm `uvx` works
The CDK-native path launches `aws-iac-mcp-server` and `ccapi-mcp-server` as
subprocesses via `uvx` (bundled with [`uv`](https://docs.astral.sh/uv/)):
```bash
uvx awslabs.aws-iac-mcp-server@latest --help   # should print usage, not error
uvx awslabs.ccapi-mcp-server@latest --help
```
If these fail, install/update `uv` before proceeding — this is a hard
dependency of `cdk_provisioning_agent`, not optional tooling.

### 6. (Terraform path only) Create an HCP Terraform account and token
Skip this if you're only demoing the CDK path.
1. Sign up for a free [HCP Terraform](https://app.terraform.io/) account and
   create an organization + workspace dedicated to this project.
2. Generate a user or team API token (Settings → Tokens).
3. Install HashiCorp's official Terraform MCP Server per its
   [current docs](https://developer.hashicorp.com/terraform/mcp-server) —
   verify the exact install/launch command there; `mcp_server/external_servers.py`
   has not been tested against a live install yet, and flags this explicitly.
4. Note the workspace's org/workspace name — `security-review-checklist`'s
   workspace-scope check (see `infra/README.md`) depends on knowing this.

### 7. Configure the project
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
# Terraform path only:
TFE_TOKEN=<your HCP Terraform API token>
TFE_ADDRESS=https://app.terraform.io
ENABLE_TF_OPERATIONS=false   # flip to true only when you intend to actually apply
```

### 8. Sanity-check before touching any cloud
Run the deterministic compliance check first — it makes no cloud calls:
```bash
python spec/check_compliance.py spec/example_submission.yaml
```
Confirm it prints `PASS`. Then try a spec that should fail (e.g., copy
`spec/example_submission.yaml`, set `public_write: true` on the bucket) and
confirm it prints `FAIL` with the right reason — this is your evidence the
guardrail actually works, worth capturing for the demo video.

### 9. Run the agent
```bash
export $(cat .env | xargs)   # or use direnv / your preferred env loader
python -m agents.orchestrator
```
State your tool preference in the request (e.g., "using CDK, deploy..." or
"using Terraform, deploy..."). Watch for the plain-English Vibe Diff summary
before anything is created — if a provisioning sub-agent tries to skip
straight to execution without it, stop and check the `provision-infra` and
`security-review-checklist` skill instructions before proceeding.

### 10. Tear down immediately after recording the demo
```bash
./scripts/teardown.sh
```
Then manually confirm in the AWS console that the S3 bucket and CloudFront
distribution are gone (CloudFront deletion requires the distribution to
finish disabling first — the script prints a reminder to re-run for this).
Finally, check the Billing console once more before walking away.

## Project layout
- `START_HERE.md` — a tiered reading path through this repo's docs,
  for humans; `AGENTS.md`/`CLAUDE.md` are the tight, always-loaded,
  AI-agent-facing context files, not a tour.
- `AGENTS.md` — shared, cross-tool foundation for any AI agent working
  in this repo (stack, conventions, hard rules, workflow, skills
  catalog); `CLAUDE.md` adds Claude-Code-specific detail on top. See
  `docs/course_concepts_and_project_structure.md` for where these came
  from and why they're shaped this way.
- `agents/` — ADK orchestrator, the provisioning router, its two sub-agents
  (`cdk_provisioning_agent`, `terraform_provisioning_agent`),
  `security_agent`, and `model_config.py` (config-driven model selection —
  see `docs/HARNESS_DESIGN.md`)
- `config/models.yaml` — which model backs which agent role
- `skills/` — Agent Skills (procedure/decision logic, not cloud access)
- `mcp_server/external_servers.py` — connection configs for the third-party
  MCP servers this project routes to (no longer hosts our own AWS server)
- `spec/` — reference architecture (BDD-style rules) + compliance checker
- `infra/` — IAM policy + resource-type allow-list for the agent's credentials
- `scripts/` — teardown script for demo cleanup
- `docs/HARNESS_DESIGN.md` — the product-level design for a multi-channel,
  multi-tenant harness (OpenClaw-inspired) that this hackathon build is one
  slice of; not built yet, see that doc for the built-vs-designed line

## Roadmap: multi-cloud and other IaC tools
This MVP covers AWS via two tool paths. Extending it means adding a new
provisioning sub-agent per cloud/tool combination, following the same
pattern (`provision-infra` skill routes to it; `security-review-checklist`
gets a path-specific check block). Real, currently-maintained MCP servers to
integrate next:

| Cloud | Tool | MCP server to integrate | Notes |
|---|---|---|---|
| GCP | native | Google-managed MCP servers (50+, GA/preview) — specifically the **GCE MCP server** for compute provisioning | Managed/remote by default as of March 2026; no self-hosting needed |
| Azure | native | **Azure MCP Server 2.0** (self-hosted/remote, 276 tools/57 services) or the newer **Azure Resource Manager MCP Server** (preview) for ARM-template-based provisioning | Choose ARM MCP Server if you want CloudFormation-style declarative parity with the AWS CDK path |
| GCP/Azure/AWS | Terraform | Same HashiCorp Terraform MCP Server already integrated — it's cloud-agnostic via Terraform providers, so no new server is needed, just new provider configs | Lowest-effort way to add a second/third cloud |

**Deprecated — don't integrate these even though they show up in search
results**: `awslabs.cdk-mcp-server` (superseded by `aws-iac-mcp-server`) and
the community `awslabs.terraform-mcp-server` with `RunTerraformCommand`
(superseded by HashiCorp's official server used here).

Also out of scope for this MVP, not yet designed: diagram-image upload and
parsing (currently a structured YAML spec is required as input), and
compute workloads (Lambda/ECS/EC2/GCE/Azure VMs) beyond static hosting.

## Security note
No API keys or credentials are committed. `.env` is gitignored; use
`.env.example` as the template. Cloud credentials should be scoped per
`infra/README.md` and used only against a disposable sandbox account.
