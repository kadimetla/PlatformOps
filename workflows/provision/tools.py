from typing import Optional

from langchain_core.tools import tool

from workflows.provision.schemas import ProfileSelection


@tool
def select_deployment_profile(selection: ProfileSelection) -> str:
    """Select one reviewed deployment profile from the provided catalog."""

    return selection.profile_id


@tool
def extract_aws_static_web_request(
    frontend_artifact_uri: Optional[str] = None,
    frontend_hostname: Optional[str] = None,
    clarifying_question: Optional[str] = None,
) -> str:
    """Extract static-web inputs or request the one missing detail."""

    return (
        f"artifact={frontend_artifact_uri} hostname={frontend_hostname} "
        f"clarifying_question={clarifying_question}"
    )
