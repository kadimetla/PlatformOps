"""Tests for the deterministic skill-matching path (docs/structured_match_rule_for_skills.md
Part F0/F0b/F0c; openspec/changes/wire-plan-request-envelope/ task groups 3-4).

Uses synthetic on-disk skills in tmp_path -- there is currently no real,
narrowly-scoped skill in skills/ to match against (provision-infra is
deliberately general-purpose, no fixed resource_types), so resolve_skill_candidates()
against the real skills/ directory correctly returns [] today. That's
expected, not a bug: the deterministic path only activates once a
SkillProposal narrowly scoped to one resource-type set gets materialized,
which hasn't happened yet in this codebase.
"""
import os

from gateway.schemas import SkillPromotionPolicy
from gateway.skill_matching import (
    find_matching_skill_path,
    normalize_resource_types,
    resolve_skill_candidates,
)
from gateway.skill_usage_store import SkillUsageStore

SPEC_S3_ONLY = {
    "app_name": "demo-blog",
    "region": "us-east-1",
    "resources": [{"type": "s3_bucket", "name": "platformops-demo-blog"}],
}


def _write_skill(base: str, skill_id: str, resource_types: list[str]):
    skill_dir = os.path.join(base, skill_id)
    os.makedirs(skill_dir, exist_ok=True)
    metadata_yaml = "\n".join(f"    - {t}" for t in resource_types)
    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(
            f"""---
name: {skill_id}
description: test skill for {skill_id}
metadata:
  resource_types:
{metadata_yaml}
---

# {skill_id}
Test skill body.
"""
        )


def _store_with_stable_skills(tmp_path, *skill_paths: str) -> SkillUsageStore:
    """A usage store where the given skill_paths are already promoted to
    'stable' (3 consecutive successes) -- the trust bar the deterministic
    path requires on top of a resource-type match."""
    store = SkillUsageStore(str(tmp_path / "usage.sqlite"))
    policy = SkillPromotionPolicy(org_id="acme")
    for path in skill_paths:
        for _ in range(3):
            store.record_skill_usage(path, "bu", "acme", "payments", True, policy)
    return store


def _empty_store(tmp_path) -> SkillUsageStore:
    return SkillUsageStore(str(tmp_path / "usage.sqlite"))


def test_normalize_resource_types_maps_lowercase_to_cfn_style():
    assert normalize_resource_types(SPEC_S3_ONLY) == {"AWS::S3::Bucket"}


def test_no_real_skill_matches_the_general_purpose_provision_infra_skill(tmp_path):
    # provision-infra is deliberately general-purpose, no fixed
    # resource_types -- this is the expected, correct state today.
    store = _empty_store(tmp_path)
    assert resolve_skill_candidates(SPEC_S3_ONLY, "payments", "acme", store) == []


def test_exact_match_at_bu_tier_wins_over_org_and_bundled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill("workspaces/payments/skills", "s3-only-skill", ["AWS::S3::Bucket"])
    _write_skill("orgs/acme/skills", "s3-only-skill-org", ["AWS::S3::Bucket"])
    store = _store_with_stable_skills(
        tmp_path,
        "workspaces/payments/skills/s3-only-skill",
        "orgs/acme/skills/s3-only-skill-org",
    )

    path = find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store)
    assert path == "workspaces/payments/skills/s3-only-skill"


def test_ambiguity_within_a_tier_fails_closed_does_not_fall_through(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill("workspaces/payments/skills", "s3-skill-a", ["AWS::S3::Bucket"])
    _write_skill("workspaces/payments/skills", "s3-skill-b", ["AWS::S3::Bucket"])
    _write_skill("orgs/acme/skills", "s3-only-skill-org", ["AWS::S3::Bucket"])
    store = _store_with_stable_skills(
        tmp_path,
        "workspaces/payments/skills/s3-skill-a",
        "workspaces/payments/skills/s3-skill-b",
        "orgs/acme/skills/s3-only-skill-org",
    )

    # two BU-tier matches -- must fail closed, NOT fall through to the
    # unambiguous org-tier match
    assert find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store) is None


def test_superset_match_does_not_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill(
        "workspaces/payments/skills",
        "s3-and-cloudfront-skill",
        ["AWS::S3::Bucket", "AWS::CloudFront::Distribution"],
    )
    store = _store_with_stable_skills(
        tmp_path, "workspaces/payments/skills/s3-and-cloudfront-skill"
    )

    assert find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store) is None


def test_falls_through_to_org_tier_when_bu_tier_has_no_skills_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill("orgs/acme/skills", "s3-only-skill-org", ["AWS::S3::Bucket"])
    store = _store_with_stable_skills(tmp_path, "orgs/acme/skills/s3-only-skill-org")

    path = find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store)
    assert path == "orgs/acme/skills/s3-only-skill-org"


def test_resolve_skill_candidates_returns_skill_path_and_loaded_skill(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill("workspaces/payments/skills", "s3-only-skill", ["AWS::S3::Bucket"])
    store = _store_with_stable_skills(tmp_path, "workspaces/payments/skills/s3-only-skill")

    candidates = resolve_skill_candidates(SPEC_S3_ONLY, "payments", "acme", store)
    assert len(candidates) == 1
    skill_path, skill = candidates[0]
    assert skill_path == "workspaces/payments/skills/s3-only-skill"
    assert skill.name == "s3-only-skill"


def test_a_provisional_skill_is_excluded_despite_matching_resource_types(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_skill("workspaces/payments/skills", "s3-only-skill", ["AWS::S3::Bucket"])
    store = _empty_store(tmp_path)  # never used -- still "provisional"

    assert find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store) is None


def test_a_demoted_skill_stops_matching_on_the_very_next_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill_path = "workspaces/payments/skills/s3-only-skill"
    _write_skill("workspaces/payments/skills", "s3-only-skill", ["AWS::S3::Bucket"])
    store = _store_with_stable_skills(tmp_path, skill_path)
    assert find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store) == skill_path

    policy = SkillPromotionPolicy(org_id="acme")
    for _ in range(5):
        store.record_skill_usage(skill_path, "bu", "acme", "payments", False, policy)

    assert find_matching_skill_path(SPEC_S3_ONLY, "payments", "acme", store) is None
