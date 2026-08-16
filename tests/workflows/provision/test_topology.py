import pytest

from workflows.provision.profiles import resolve_profile
from workflows.provision.topology import TopologyValidationError, validate_topology


REGISTERED = {
    "aws.s3.private_bucket",
    "aws.cloudfront.s3_distribution",
    "aws.s3.cloudfront_oac_policy",
}


def test_reviewed_static_web_profile_loads_and_validates():
    registration = resolve_profile("aws-static-web")
    spec = registration.load_topology()

    validated = validate_topology(
        spec,
        profile_id=registration.profile_id,
        provider=registration.provider,
        registered_units=REGISTERED,
    )

    assert validated.root_ids == ["assets"]
    assert validated.leaf_ids == ["origin_policy"]
    assert validated.predecessors_by_target["origin_policy"] == ["assets", "cdn"]


def test_unknown_unit_fails_closed():
    registration = resolve_profile("aws-static-web")
    spec = registration.load_topology().model_dump(mode="python")
    spec["units"] = [{"id": "bad", "uses": "aws.unknown"}]
    spec = registration.load_topology().model_validate(spec)

    with pytest.raises(TopologyValidationError, match="unknown topology unit"):
        validate_topology(
            spec,
            profile_id=registration.profile_id,
            provider=registration.provider,
            registered_units=REGISTERED,
        )


def test_cycle_fails_closed():
    registration = resolve_profile("aws-static-web")
    spec = registration.load_topology().model_dump(mode="python")
    spec["edges"] = [
        {"from": "assets", "to": "cdn"},
        {"from": "cdn", "to": "assets"},
    ]
    spec = registration.load_topology().model_validate(spec)

    with pytest.raises(TopologyValidationError, match="acyclic"):
        validate_topology(
            spec,
            profile_id=registration.profile_id,
            provider=registration.provider,
            registered_units=REGISTERED,
        )
