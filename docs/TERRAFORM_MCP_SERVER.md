## Status
Research/verification doc, not a design proposal. Verified HashiCorp's
`terraform-mcp-server` against current upstream docs, per `AGENTS.md`'s
workflow rule 3 ("verify third-party MCP server integration points...
before relying on them"). Found and fixed a bug in
`mcp_server/external_servers.py:44-52`, described below.

## Real vs. designed
| Item | Status |
|---|---|
| `TERRAFORM_MCP_SERVER` config exists in code | Real (`mcp_server/external_servers.py:44-52`) |
| `args=["stdio"]` is a correct invocation | Fixed — was `["-transport=stdio"]`, not a recognized flag on any documented version of this binary |
| `TFE_TOKEN`/`TFE_ADDRESS`/`ENABLE_TF_OPERATIONS` env var names | Correct as coded |
| This project has executed the integration | Not yet — code comment says so, confirmed still true |

## The bug (fixed)
`mcp_server/external_servers.py:44-52` previously had:
```python
TERRAFORM_MCP_SERVER = StdioServerParameters(
    command="terraform-mcp-server",
    args=["-transport=stdio"],
    ...
)
```
The real CLI takes a subcommand, not a flag:
```
terraform-mcp-server stdio [--log-file PATH] [--log-level info] [--log-format text] [--toolsets <csv>] [--tools <csv>]
```
`args` is now `["stdio"]`.

## Verified environment variables
| Var | Purpose | Default |
|---|---|---|
| `TFE_TOKEN` | HCP Terraform / TFE API token | none, required |
| `TFE_ADDRESS` | HCP Terraform / TFE base URL | `https://app.terraform.io` |
| `ENABLE_TF_OPERATIONS` | Unlocks write/destructive tools | `false` |
| `TFE_SKIP_TLS_VERIFY` | Skip TLS verification | `false` |

`ENABLE_TF_OPERATIONS` is the write gate — every tool listed under
"Requires ENABLE_TF_OPERATIONS=true" below is inert until it's set,
which already matches this repo's deny-by-default hard rule
(`AGENTS.md` → Architecture principles) without any extra code needed.

## Tool inventory, by toolset (`--toolsets registry,registry-private,terraform,all,default`)

**registry** (public Terraform Registry lookups, read-only):
`search_providers`, `get_provider_details`, `get_latest_provider_version`,
`search_modules`, `get_module_details`, `get_latest_module_version`,
`search_policies`, `get_policy_details`

**registry-private** (org-private registry, read-only):
`search_private_modules`, `get_private_module_details`,
`search_private_providers`, `get_private_provider_details`

**terraform** (HCP Terraform / TFE — org/project/workspace/run operations):
- Read-only: `list_terraform_orgs`, `list_terraform_projects`,
  `list_workspaces`, `get_workspace_details`, `list_runs`,
  `get_run_details`, `get_workspace_policy_sets`,
  `get_token_permissions`, `get_plan_json_output`, `get_plan_details`,
  `get_plan_logs`, `get_apply_details`, `get_apply_logs`,
  `list_variable_sets`, `list_workspace_variables`,
  `read_workspace_tags`, `list_stacks`, `get_stack_details`
- Requires `ENABLE_TF_OPERATIONS=true`: `create_workspace`,
  `update_workspace`, `delete_workspace_safely`, `create_run`,
  `action_run` (apply/discard/cancel), `create_variable_set`,
  `create_variable_in_variable_set`, `delete_variable_in_variable_set`,
  `attach_variable_set_to_workspaces`,
  `detach_variable_set_from_workspaces`, `create_workspace_variable`,
  `update_workspace_variable`, `create_workspace_tags`,
  `attach_policy_set_to_workspace`

## HCP Terraform workspaces vs. CLI workspaces
Every `terraform` toolset tool above (`list_workspaces`,
`create_workspace`, ...) operates on **HCP Terraform / Terraform
Enterprise workspaces**, a different concept from CLI-native
`terraform workspace` despite the shared name. Conflating them would
misdesign any future workflow that touches both this MCP server and a
raw `terraform` CLI invocation.

| | CLI workspace (`terraform workspace`) | HCP Terraform workspace (this MCP server's target) |
|---|---|---|
| What it is | A named state file within one backend | "A group of infrastructure resources managed by Terraform" — config, vars, state, run history, VCS link |
| Hierarchy | None — flat within a backend | Organization → Project (optional) → Workspace |
| Isolation guarantee | None — HashiCorp: "not appropriate for system decomposition or deployments requiring separate credentials and access controls" | Real: RBAC boundary, separate credentials/vars per workspace |
| Where state lives | Local/remote backend, one file per workspace | Workspace-managed, with full state history |
| Run execution | Wherever `terraform apply` is invoked | On HCP Terraform's disposable VMs (remote operations, default) inside that workspace's isolated context |

Implication: don't use CLI `terraform workspace new <env>` as a
substitute for HCP Terraform workspace isolation in any workflow this
project builds — the CLI form carries no RBAC or credential boundary,
per HashiCorp's own docs.

## Sources
- [Terraform MCP Server overview](https://developer.hashicorp.com/terraform/mcp-server)
- [Terraform MCP Server deploy overview](https://developer.hashicorp.com/terraform/docs/tools/mcp-server/deploy)
- [terraform-mcp-server GitHub repo / README](https://github.com/hashicorp/terraform-mcp-server)
- [Terraform MCP Server tool reference](https://developer.hashicorp.com/terraform/mcp-server/reference)
- [HCP Terraform workspaces](https://developer.hashicorp.com/terraform/cloud-docs/workspaces)
- [Terraform CLI-native state workspaces](https://developer.hashicorp.com/terraform/language/state/workspaces)

## How this relates to the existing docs
Extends `AGENTS.md`'s `mcp_server/` convention entry and its Workflow
rule 3 (verify MCP integration points before relying on them) with the
actual verification. Doesn't repeat the AWS IaC/CCAPI MCP server
config in the same file — those are unverified separately and not
covered here. Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
