## Status
Entry point / document map. Created new on this branch (per
`CLAUDE.md`'s process) — `docs/` did not exist here before. Points to
docs that carry real content; this file itself holds no design
reasoning, only the map.

## Document map
| Doc | Covers | Status |
|---|---|---|
| [TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md) | HashiCorp `terraform-mcp-server` integration: verified CLI/env, tool inventory, HCP Terraform workspace concepts | Verified against current upstream docs; one code bug found and fixed |
| [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) | Request intake classification, bounded caller-side clarification (return-and-re-invoke, no in-graph interrupt), `<org>:<bu>` → project → workspace scope model, deterministic per-scope routing | Designed only, corrected in place by the 2026-07-27 deep-dive explore; no workflow or gateway code exists yet |

## How this relates to the existing docs
`AGENTS.md` names this file as the entry point once a non-trivial
design gets written down (`## Conventions` → `docs/`). A more advanced
exploration of the same LangGraph direction exists on
`design/harness-architecture`, which has its own `docs/HARNESS_DESIGN.md`
— that branch is not merged here and its document map is a separate,
unrelated index; don't confuse the two.
