import asyncio

from langchain_core.messages import AIMessage

from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.schemas import Scope, ScopeHint, TenantRef
from workflows.provision.graph import prepare_provision_request
from workflows.provision.schemas import ProvisionInvocation


def _scope():
    return Scope(org="aiq", bu="it", project="invoices", workspace="dev")


def _invocation(scope_hint=None):
    return ProvisionInvocation(
        raw_text=(
            "deploy s3://releases/invoices-ui.tar.gz at "
            "invoices.dev.example.com"
        ),
        scope_hint=scope_hint
        or ScopeHint(
            tenant=TenantRef(org="aiq", bu="it"),
            project="invoices",
            workspace="dev",
        ),
    )


def _grant():
    return ExecutionGrant(
        scope=_scope(), provider="aws", capability=Capability.APPLY_LIMITED
    )


def _tool_call(name, **args):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": name}]
    )


class _DirectFake:
    def __init__(self, *responses):
        self.responses = list(responses)

    async def ainvoke(self, _messages):
        return self.responses.pop(0)

    def bind_tools(self, _tools, **_kwargs):
        return self


def test_prepares_a_typed_static_web_request_without_execution():
    model = _DirectFake(
            _tool_call("select_deployment_profile", profile_id="aws-static-web"),
            _tool_call(
                "extract_aws_static_web_request",
                frontend_artifact_uri="s3://releases/invoices-ui.tar.gz",
                frontend_hostname="invoices.dev.example.com",
            ),
    )

    result = asyncio.run(
        prepare_provision_request(_invocation(), model, [_scope()], [_grant()])
    )

    assert result.ready is True
    assert result.profile_id == "aws-static-web"
    assert result.application_request.scope == _scope()
    assert result.application_request.frontend_hostname == "invoices.dev.example.com"


def test_scope_failure_stops_before_any_model_call():
    model = _DirectFake()

    result = asyncio.run(prepare_provision_request(_invocation(), model, [_scope()], []))

    assert result.unavailable_reason == "target not found or not accessible"
    assert result.profile_id is None


def test_missing_scope_fields_returns_clarification_before_model_call():
    model = _DirectFake()
    hint = ScopeHint(tenant=TenantRef(org="aiq", bu="it"))

    result = asyncio.run(
        prepare_provision_request(_invocation(hint), model, [_scope()], [_grant()])
    )

    assert result.clarification_questions[0].field == "scope"


def test_missing_profile_input_returns_clarification():
    model = _DirectFake(
            _tool_call("select_deployment_profile", profile_id="aws-static-web"),
            _tool_call(
                "extract_aws_static_web_request",
                frontend_artifact_uri="s3://releases/invoices-ui.tar.gz",
                clarifying_question="Which hostname should serve the frontend?",
            ),
    )

    result = asyncio.run(
        prepare_provision_request(_invocation(), model, [_scope()], [_grant()])
    )

    assert result.ready is False
    assert result.clarification_questions[0].question == (
        "Which hostname should serve the frontend?"
    )
