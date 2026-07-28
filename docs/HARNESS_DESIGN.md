## Status
Entry point / document map. Created new on this branch (per
`CLAUDE.md`'s process) — `docs/` did not exist here before. Points to
docs that carry real content; this file itself holds no design
reasoning, only the map.

## Document map
| Doc | Covers | Status |
|---|---|---|
| [TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md) | HashiCorp `terraform-mcp-server` integration: verified CLI/env, tool inventory, HCP Terraform workspace concepts | Verified against current upstream docs; one code bug found and fixed |
| [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) | Request intake classification, bounded caller-side clarification (return-and-re-invoke, no in-graph interrupt), `<org>:<bu>` → project → workspace scope model, deterministic per-scope routing, request-time cloud access flow (AWS/Azure/GCP) | Designed only, corrected/extended in place since the 2026-07-27 deep-dive explore; no workflow, gateway, or auth code exists yet |
| [ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md) | Login-time access discovery (OIDC login → provider principal resolution → per-cloud entitlement discovery → capability normalization → session grants), the capability ladder, `effective_access = min(grant, ceiling)`, discovery/execution/bootstrap identity separation, new-project bootstrap, `gateway/policy/` registry | Designed only, provider APIs verified against current docs 2026-07-28; three gaps found and corrected during verification; no auth or gateway code exists yet |
| [EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) | Execution-time credential acquisition: runtime root identity (Layer 0), per-workspace execution identities + delegation (Layer 1), JIT short-lived tokens (Layer 2), the Azure narrowing asymmetry, pre-flight checks (resume re-validation, plan-digest binding), no-tokens-in-graph-state rule, the approval gate (self-looping interrupt node, PlatformOps-native approval authority, staleness/revocation rules) | Designed only; mechanisms standard but flagged verify-before-build; no executor code exists yet |
| [BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md) | How the identities get created: the bootstrap ladder (Level -1 manual → org/BU as PR-reviewed config → automated project/workspace bootstrap), bootstrap-as-provision with a disjoint identity-only allow-list, never LLM-routed, registry-written-last with lifecycle state, per-cloud escalation ceilings (permissions boundaries / role allow-lists), teardown deferred as a separate path | Designed only; per-cloud ceiling mechanisms flagged verify-before-build; nothing implemented |

## How this relates to the existing docs
`AGENTS.md` names this file as the entry point once a non-trivial
design gets written down (`## Conventions` → `docs/`). A more advanced
exploration of the same LangGraph direction exists on
`design/harness-architecture`, which has its own `docs/HARNESS_DESIGN.md`
— that branch is not merged here and its document map is a separate,
unrelated index; don't confuse the two.
