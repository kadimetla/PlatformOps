from gateway.auth.domain_discovery import (
    ActiveOrganizationDomain,
    OrganizationIdpConfiguration,
    PostLoginDomainDiscoveryService,
    PostLoginJourney,
)


class FakeDomains:
    def __init__(self, domain: ActiveOrganizationDomain | None) -> None:
        self.domain = domain
        self.lookups = []

    def find_active_domain(self, canonical_domain: str):
        self.lookups.append(canonical_domain)
        return self.domain if self.domain and self.domain.canonical_domain == canonical_domain else None


def test_active_verified_domain_returns_member_onboarding_journey_only():
    domains = FakeDomains(ActiveOrganizationDomain(organization_id="org_acme", canonical_domain="acme.example"))
    result = PostLoginDomainDiscoveryService(domains=domains).discover("Alice@ACME.example")

    assert result.journeys == [PostLoginJourney.ORGANIZATION_MEMBER_ONBOARDING]
    assert result.organization_id == "org_acme"
    assert domains.lookups == ["acme.example"]


def test_unknown_domain_returns_safe_personal_or_business_journeys_only():
    result = PostLoginDomainDiscoveryService(domains=FakeDomains(None)).discover("alice@unknown.example")

    assert result.journeys == [
        PostLoginJourney.PERSONAL_ORGANIZATION_CREATION,
        PostLoginJourney.BUSINESS_ORGANIZATION_CLAIM,
    ]
    assert result.organization_id is None


def test_configured_organization_idp_is_a_journey_not_a_membership():
    domains = FakeDomains(ActiveOrganizationDomain(
        organization_id="org_acme",
        canonical_domain="acme.example",
        idp=OrganizationIdpConfiguration(
            issuer="https://id.acme.example", audience="platformops-acme"
        ),
    ))

    result = PostLoginDomainDiscoveryService(domains=domains).discover("alice@acme.example")

    assert result.journeys == [PostLoginJourney.ORGANIZATION_IDP_AUTHENTICATION]
    assert result.organization_id == "org_acme"
    assert result.idp is not None
    assert result.idp.issuer == "https://id.acme.example"
