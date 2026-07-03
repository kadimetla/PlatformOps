# Verify import paths/signatures against the installed google-adk version.
from google.adk.agents import Agent

from .cdk_provisioning_agent import cdk_provisioning_agent
from .terraform_provisioning_agent import terraform_provisioning_agent

provisioning_agent = Agent(
    name="provisioning_agent",
    model="gemini-2.5-flash",
    description="Routes a provisioning request to the CDK-native or Terraform sub-agent based on the user's tool preference.",
    instruction=(
        "Follow the 'provision-infra' skill's Step 0 to determine the "
        "user's IaC tool preference. Delegate to cdk_provisioning_agent for "
        "'cdk' (the default when unstated), or terraform_provisioning_agent "
        "for 'terraform'. Do not draft or execute a provisioning plan "
        "yourself — always delegate to the matching sub-agent."
    ),
    sub_agents=[cdk_provisioning_agent, terraform_provisioning_agent],
)
