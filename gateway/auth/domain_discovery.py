"""Post-login organization-domain discovery; journeys only, never grants."""
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gateway.auth.registration import canonicalize_email


class ActiveOrganizationDomain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(min_length=1)
    canonical_domain: str = Field(min_length=1)
    idp: "OrganizationIdpConfiguration | None" = None


class OrganizationIdpConfiguration(BaseModel):
    """Trusted organization configuration; browser payload never supplies it."""

    model_config = ConfigDict(extra="forbid")

    issuer: str = Field(min_length=1)
    audience: str = Field(min_length=1)


class ActiveOrganizationDomainLookup(Protocol):
    def find_active_domain(self, canonical_domain: str) -> ActiveOrganizationDomain | None: ...


class PostLoginJourney(str, Enum):
    ORGANIZATION_IDP_AUTHENTICATION = "organization_idp_authentication"
    ORGANIZATION_MEMBER_ONBOARDING = "organization_member_onboarding"
    PERSONAL_ORGANIZATION_CREATION = "personal_organization_creation"
    BUSINESS_ORGANIZATION_CLAIM = "business_organization_claim"


class PostLoginDiscoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journeys: list[PostLoginJourney]
    organization_id: str | None = None
    idp: OrganizationIdpConfiguration | None = None


class PostLoginDomainDiscoveryService:
    def __init__(self, *, domains: ActiveOrganizationDomainLookup) -> None:
        self._domains = domains

    def discover(self, email: str) -> PostLoginDiscoveryResult:
        _, domain = canonicalize_email(email)
        match = self._domains.find_active_domain(domain)
        if match is not None:
            if match.idp is not None:
                return PostLoginDiscoveryResult(
                    journeys=[PostLoginJourney.ORGANIZATION_IDP_AUTHENTICATION],
                    organization_id=match.organization_id,
                    idp=match.idp,
                )
            return PostLoginDiscoveryResult(
                journeys=[PostLoginJourney.ORGANIZATION_MEMBER_ONBOARDING],
                organization_id=match.organization_id,
            )
        return PostLoginDiscoveryResult(
            journeys=[
                PostLoginJourney.PERSONAL_ORGANIZATION_CREATION,
                PostLoginJourney.BUSINESS_ORGANIZATION_CLAIM,
            ]
        )
