from pydantic import ValidationError

from gateway.auth.schemas import ExecutionGrant
from gateway.scope import ScopeResolutionStatus, resolve_scope
from gateway.schemas import ClarificationQuestion, Scope
from workflows.provision.schemas import (
    AwsStaticWebProvisionRequest,
    ProfileSelection,
    ProvisionDraft,
)
from workflows.provision.state import ProvisionState
from workflows.provision.tools import (
    extract_aws_static_web_request,
    select_deployment_profile,
)


def build_resolve_scope(
    known_workspaces: list[Scope], execution_grants: list[ExecutionGrant]
):
    async def resolve_scope_node(state: ProvisionState) -> dict:
        resolution = resolve_scope(
            state["invocation"].scope_hint, known_workspaces, execution_grants
        )
        if resolution.status == ScopeResolutionStatus.RESOLVED:
            return {
                "scope": resolution.scope,
                "result": ProvisionDraft(scope=resolution.scope),
            }
        if resolution.status == ScopeResolutionStatus.CLARIFICATION_REQUIRED:
            return {
                "result": ProvisionDraft(
                    clarification_questions=[resolution.clarification]
                )
            }
        return {
            "result": ProvisionDraft(unavailable_reason=resolution.public_reason)
        }

    return resolve_scope_node


def build_select_profile(model):
    planner = model.bind_tools(
        [select_deployment_profile], tool_choice="select_deployment_profile"
    )

    async def select_profile(state: ProvisionState) -> dict:
        response = await planner.ainvoke(
            [
                (
                    "system",
                    "Select exactly one reviewed deployment profile. The only "
                    "available profile is aws-static-web. Call "
                    "select_deployment_profile exactly once; do not provide units, "
                    "edges, credentials, account IDs, or infrastructure code.",
                ),
                ("user", state["invocation"].raw_text),
            ]
        )
        calls = getattr(response, "tool_calls", None) or []
        try:
            if len(calls) != 1 or calls[0].get("name") != "select_deployment_profile":
                raise ValueError("expected one profile-selection tool call")
            args = calls[0].get("args", {})
            selection = ProfileSelection.model_validate(args.get("selection", args))
        except (ValidationError, ValueError):
            result = state["result"].model_copy(
                update={
                    "clarification_questions": [
                        ClarificationQuestion(
                            field="profile_id",
                            question="Select a supported deployment profile.",
                            choices=["aws-static-web"],
                        )
                    ]
                }
            )
            return {"result": result}

        return {
            "profile_id": selection.profile_id,
            "result": state["result"].model_copy(
                update={"profile_id": selection.profile_id}
            ),
        }

    return select_profile


def build_extract_profile_request(model):
    extractor = model.bind_tools(
        [extract_aws_static_web_request],
        tool_choice="extract_aws_static_web_request",
    )

    async def extract_profile_request(state: ProvisionState) -> dict:
        response = await extractor.ainvoke(
            [
                (
                    "system",
                    "Extract frontend_artifact_uri and frontend_hostname for the "
                    "selected aws-static-web profile. Call "
                    "extract_aws_static_web_request exactly once. If either value "
                    "is missing, set clarifying_question instead of guessing.",
                ),
                ("user", state["invocation"].raw_text),
            ]
        )
        calls = getattr(response, "tool_calls", None) or []
        args = calls[0].get("args", {}) if len(calls) == 1 else {}
        artifact = args.get("frontend_artifact_uri")
        hostname = args.get("frontend_hostname")
        if (
            len(calls) != 1
            or calls[0].get("name") != "extract_aws_static_web_request"
            or not artifact
            or not hostname
        ):
            question = args.get("clarifying_question") or (
                "Provide the frontend artifact URI and frontend hostname."
            )
            result = state["result"].model_copy(
                update={
                    "clarification_questions": [
                        ClarificationQuestion(field="application_request", question=question)
                    ]
                }
            )
            return {"result": result}

        request = AwsStaticWebProvisionRequest(
            scope=state["scope"],
            frontend_artifact_uri=artifact,
            frontend_hostname=hostname,
        )
        return {
            "result": state["result"].model_copy(
                update={"application_request": request}
            )
        }

    return extract_profile_request


async def continue_if_ready(state: ProvisionState) -> str:
    if state["result"].clarification_questions or state["result"].unavailable_reason:
        return "stop"
    return "continue"
