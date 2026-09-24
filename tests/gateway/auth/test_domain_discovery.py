from gateway.auth.domain_discovery import (
    ActiveOrganizationDomain,
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
