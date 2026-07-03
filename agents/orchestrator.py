# Verify import paths/signatures against the installed google-adk version.
from google.adk.agents import Agent

from .provisioning_agent import provisioning_agent
from .security_agent import security_agent

root_agent = Agent(
    name="platformops_orchestrator",
    model="gemini-2.5-flash",
    description="Routes infra requests to the provisioning agent, gated by the security agent's approval.",
    instruction=(
        "You are the entry point for platform-ops requests. Given a structured infra spec "
        "(see spec/reference_architecture.md for the compliance rules it must satisfy), "
        "delegate to provisioning_agent to draft a plan, then require security_agent's "
        "explicit approval before any AWS-modifying tool call is allowed to execute. "
        "If security_agent rejects the plan, return its reason to the user instead of retrying silently."
    ),
    sub_agents=[provisioning_agent, security_agent],
)
