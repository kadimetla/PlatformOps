from typing import Literal

from pydantic import BaseModel, Field

from gateway.schemas import ClarificationQuestion, Scope, ScopeHint


class ProfileSelection(BaseModel):
    profile_id: Literal["aws-static-web"]


class AwsStaticWebProvisionRequest(BaseModel):
    profile_id: Literal["aws-static-web"] = "aws-static-web"
    scope: Scope
    frontend_artifact_uri: str = Field(min_length=1)
    frontend_hostname: str = Field(min_length=1)


class ProvisionInvocation(BaseModel):
    raw_text: str = Field(min_length=1)
    scope_hint: ScopeHint


class ProvisionDraft(BaseModel):
    scope: Scope | None = None
    profile_id: str | None = None
    application_request: AwsStaticWebProvisionRequest | None = None
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    unavailable_reason: str | None = None

    @property
    def ready(self) -> bool:
        return (
            self.application_request is not None
            and not self.clarification_questions
            and self.unavailable_reason is None
        )
