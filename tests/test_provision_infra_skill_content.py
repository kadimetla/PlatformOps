"""Proves docs/skill_loading_and_enforcement_gap.md's Finding 4 is
closed for skills/provision-infra: the real, bundled skill (not a
synthetic test fixture) now has metadata.resource_types and a real
scripts/ template for both toolchains, and the deterministic zero-LLM
path can match and fill it.

Also documents, rather than hides, a second real gap this surfaced:
nothing in production code ever calls SkillUsageStore.record_skill_usage()
(confirmed by repo-wide grep -- every call site is a test). A bundled
skill therefore starts, and stays, 'provisional' forever in a real
running system; find_matching_skill_path() requires 'stable'. The tests
below reproduce that exactly: match fails until the test manually
promotes the skill (the same workaround every other skill-matching test
already uses), proving the skill's *content* is correct while leaving
the lifecycle-promotion wiring gap visibly unresolved, not silently
patched over.
"""
import tempfile

from gateway.schemas import SkillPromotionPolicy, WorkspaceBundle
from gateway.skill_matching import find_matching_skill_path, resolve_skill_candidates
from gateway.skill_usage_store import SkillUsageStore
from workflows.drafting.skill_fill import run_deterministic_skill_fill
from workflows.drafting.skill_loading import load_skill_from_dir

SPEC = {
    "app_name": "demo-blog",
    "region": "us-east-1",
    "estimated_monthly_usd": 1.0,
    "bucket_name": "platformops-demo-blog",
    "resources": [
        {"type": "s3_bucket", "name": "platformops-demo-blog", "public_write": False}
    ],
}


def _store() -> SkillUsageStore:
    return SkillUsageStore(tempfile.mktemp(suffix=".db"))


def _promote_to_stable(store: SkillUsageStore, skill_path: str) -> None:
    policy = SkillPromotionPolicy(org_id="acme")
    for _ in range(policy.consecutive_success_limit):
        store.record_skill_usage(skill_path, "bundled", "acme", None, True, policy)


def test_real_skill_content_is_loadable_and_correctly_shaped():
    skill = load_skill_from_dir("skills/provision-infra")
    assert skill.frontmatter.metadata.get("resource_types") == ["AWS::S3::Bucket"]
    assert "main.tf" in skill.resources.list_scripts()
    assert "template.yaml" in skill.resources.list_scripts()


def test_provisional_skill_does_not_match_the_deterministic_path(tmp_path, monkeypatch):
    """Documents the lifecycle-promotion wiring gap: a freshly bundled
    skill is 'provisional' by default and nothing in production code
    ever promotes it, so it can never win here without the manual
    promotion tests below perform."""
    store = _store()
    path = find_matching_skill_path(SPEC, "payments", "acme", store)
    assert path is None


def test_stable_skill_matches_and_fills_for_both_toolchains():
    store = _store()
    _promote_to_stable(store, "skills/provision-infra")

    candidates = resolve_skill_candidates(SPEC, "payments", "acme", store)
    assert len(candidates) == 1
    skill_path, skill = candidates[0]
    assert skill_path == "skills/provision-infra"

    bundle = WorkspaceBundle(bundle_id="acme-payments", allowed_resource_types=["AWS::S3::Bucket"])

    tf_spec = {**SPEC, "toolchain": "terraform"}
    tf_draft, tf_intents = run_deterministic_skill_fill(skill, tf_spec, bundle)
    assert "main.tf" in tf_draft
    assert 'bucket_name = "platformops-demo-blog"' in tf_draft
    assert tf_intents[0]["resource_type"] == "AWS::S3::Bucket"

    cdk_spec = {**SPEC, "toolchain": "cdk"}
    cdk_draft, cdk_intents = run_deterministic_skill_fill(skill, cdk_spec, bundle)
    assert "template.yaml" in cdk_draft
    assert 'bucket_name = "platformops-demo-blog"' in cdk_draft
    assert cdk_intents[0]["resource_type"] == "AWS::S3::Bucket"
