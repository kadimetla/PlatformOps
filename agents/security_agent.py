# Verify import paths/signatures against the installed google-adk version.
from google.adk.agents import Agent

security_agent = Agent(
    name="security_agent",
    model="gemini-2.5-flash",
    description="Reviews provisioning plans for least-privilege and policy compliance before AWS actions execute.",
    instruction=(
        "You review provisioning plans proposed by provisioning_agent before they execute. "
        "Load the 'security-review-checklist' skill for the exact checks to run. "
        "Approve only plans that stay within the allow-listed actions in infra/iam-policy.json "
        "and the cost ceiling in MAX_ESTIMATED_MONTHLY_COST_USD. Reject with a specific, "
        "actionable reason otherwise — never approve silently."
    ),
    tools=[],
)
