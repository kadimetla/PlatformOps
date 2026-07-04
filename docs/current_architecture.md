# Current PlatformOps Agentic Architecture

This document provides a deep dive into the **existing architecture** of the [PlatformOps](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/README.md) system. It explains how the multi-agent graph, deterministic validation engines, and Model Context Protocol (MCP) servers interact to securely provision infrastructure.

---

## 1. Core Multi-Agent Topology (ADK Graph)

Instead of a single large prompt trying to perform all tasks, PlatformOps divides responsibilities among five specialized agents in a hierarchical graph using the **Google Agent Development Kit (ADK)**:

```mermaid
graph TD
  User([User Request / Spec]) --> Orchestrator
  
  subgraph ADK Agent Graph
    Orchestrator[platformops_orchestrator<br/>orchestration tier]
    ProvisionRouter[provisioning_agent<br/>routing tier]
    CDKAgent[cdk_provisioning_agent<br/>execution tier]
    TFAgent[terraform_provisioning_agent<br/>execution tier]
    SecurityAgent[security_agent<br/>review tier]
  end

  subgraph Deterministic Layer
    Compliance[check_compliance.py]
  end

  subgraph MCP Tools
    CDKTools[aws-iac-mcp-server<br/>read-only validation]
    CCAPITools[ccapi-mcp-server<br/>mutating AWS Cloud Control]
    TFTools[Terraform MCP Server<br/>HCP Terraform runs]
  end

  Orchestrator --> Compliance
  Orchestrator --> ProvisionRouter
  Orchestrator --> SecurityAgent
  
  ProvisionRouter --> CDKAgent
  ProvisionRouter --> TFAgent

  CDKAgent --> CDKTools
  CDKAgent --> CCAPITools
  TFAgent --> TFTools
```

### The Role-Based Splits:
1. **[platformops_orchestrator](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/agents/orchestrator.py#L8-L20) (Orchestration)**: Serves as the top-level entry point. It manages the overall state of the execution lifecycle, invokes compliance checks, gates operations behind the security review, and returns the final report to the user.
2. **[provisioning_agent](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/agents/provisioning_agent.py#L8-L21) (Routing)**: A lightweight router that reads the user's input to determine their preferred Infrastructure as Code (IaC) tool (CDK vs. Terraform) and delegates to the appropriate specialist.
3. **[cdk_provisioning_agent](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/agents/cdk_provisioning_agent.py#L9-L25) (CDK Specialist)**: Operates the AWS Cloud Control API path. It designs CloudFormation templates and runs linting/compliance validation tools.
4. **[terraform_provisioning_agent](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/agents/terraform_provisioning_agent.py#L9-L22) (Terraform Specialist)**: Operates the HCP Terraform path. It writes `.tf` configurations and communicates with HCP workspaces.
5. **[security_agent](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/agents/security_agent.py#L6-L18) (Security Reviewer)**: A non-executing auditor. It has **no tool access** and acts purely on reasoning to evaluate proposed plan changes against static policy definitions.

---

## 2. Separation of Concerns: Skills vs. MCP

The architecture separates *logic/procedure* from *action/reach* using two concepts:

* **Agent Skills (`skills/`)**: Encoded in markdown files (e.g., [provision-infra/SKILL.md](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/skills/provision-infra/SKILL.md) and [security-review-checklist/SKILL.md](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/skills/security-review-checklist/SKILL.md)), skills represent the deterministic step-by-step procedures that agents are instructed to follow.
* **MCP Servers (`mcp_server/`)**: Servers run as independent subprocesses providing standardized JSON-RPC endpoints. They supply the actual "reach" to talk to APIs (AWS and HashiCorp). The agents invoke these MCP tools to execute commands.

---

## 3. The Step-by-Step Request Lifecycle

When a user submits a request (e.g., *"Deploy a static web portal using CDK"*), the system progresses through the following steps:

```
[Inbound Request]
        │
        ▼
 1. COMPLIANCE PREFLIGHT ──► Runs spec/check_compliance.py (No LLM call)
        │
        ▼ (PASS)
 2. PLAN DRAFTING ─────────► provisioning_agent delegates to cdk_provisioning_agent
        │                    ├─ Synthesizes CloudFormation template
        │                    └─ Runs validation tools (cfn-lint, cfn-guard)
        │
        ▼ (Valid)
 3. VIBE DIFF GENERATION ──► cdk_provisioning_agent drafts plain-English change summary
        │                    and halts execution
        │
        ▼
 4. SECURITY REVIEW ───────► security_agent evaluates Vibe Diff + static policy files
        │                    ├─ Checks cost ceiling ($5 ceiling)
        │                    ├─ Checks region (us-east-1 only)
        │                    ├─ Checks allowed-resource-types.json
        │                    └─ Checks iam-policy.json
        │
        ▼ (APPROVED)
 5. EXECUTION & VERIFY ────► cdk_provisioning_agent executes ccapi create_resource,
                             calls get_resource to verify, and returns final URL
```

---

## 4. Defense-in-Depth Guardrail Layering

Security is enforced at multiple layers to prevent a single point of failure (such as an LLM reasoning error or prompt injection) from deploying unauthorized resources:

```
[Agent Intent]
     │
     ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Compliance Script Guardrail                              │
│    (Deterministic spec check: region, cost, naming prefix)   │
└────────────────────────────┬────────────────────────────────┘
                             │ (Pass)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Security Agent Check                                     │
│    (LLM validation of Vibe Diff plan text against checklists)│
└────────────────────────────┬────────────────────────────────┘
                             │ (Pass)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Application Allow-List                                   │
│    (Allowed CloudFormation resource types list)             │
└────────────────────────────┬────────────────────────────────┘
                             │ (Pass)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Cloud IAM Policy                                         │
│    (AWS IAM policy bounds credentials used by MCP process)  │
└────────────────────────────┬────────────────────────────────┘
                             │ (Allowed by AWS)
                             ▼
                     [Deployed Cloud]
```

### The Layer Safeguards:
1. **Deterministic Prefilter**: [check_compliance](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/spec/check_compliance.py#L15-L38) blocks S3 public-write and forces CloudFront HTTP-to-HTTPS redirect rule validation before agents plan the build.
2. **Double Allow-Lists for CDK/CCAPI**: 
   * [iam-policy.json](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/infra/iam-policy.json) restricts AWS account actions (IAM tier).
   * [allowed-resource-types.json](file:///opt/wecan/aiml_learning_gang_ws/vibecoding_ws/capstone_project/infra/allowed-resource-types.json) restricts target CloudFormation types (App tier). This blocks the agent from requesting resources like `AWS::EC2::Instance` even if IAM allows Cloud Control API actions.
3. **Operator Control Switch for Terraform**: On the Terraform path, the system requires the environment variable `ENABLE_TF_OPERATIONS=true` to be set by the human operator. The agent cannot toggle this flag itself, serving as an operational kill-switch.
