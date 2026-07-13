"""Deterministic skill-candidate resolution for the zero-LLM matching
path. Verified NOT to use SkillToolset/SkillRegistry -- that mechanism
is LLM-mediated at every layer (docs/structured_match_rule_for_skills.md
Part F0). Uses ADK's real list_skills_in_dir()/load_skill_from_dir()
directly instead (Part F0b): a cheap, frontmatter-only listing pass,
then one full load only for the single winning candidate.
"""
from typing import Optional

from google.adk.skills import Frontmatter, Skill, list_skills_in_dir, load_skill_from_dir

from .skill_usage_store import SkillUsageStore

# Matches infra/allowed-resource-types.json's CFN-style convention, not
# spec/example_submission.yaml's lowercase one -- bridges the two.
# Extend as infra/allowed-resource-types.json grows.
SPEC_TYPE_TO_CFN_TYPE = {
    "s3_bucket": "AWS::S3::Bucket",
    "cloudfront_distribution": "AWS::CloudFront::Distribution",
}


def normalize_resource_types(spec: dict) -> set[str]:
    """Maps spec['resources'][*]['type'] (lowercase convention) to the
    CFN-style set skill Frontmatter.metadata['resource_types'] declares."""
    return {SPEC_TYPE_TO_CFN_TYPE[r["type"]] for r in spec["resources"]}


def load_skills_in_tier(tier_dir: str) -> dict[str, Frontmatter]:
    """Cheap, frontmatter-only listing -- verified real ADK function,
    non-recursive (one directory level), soft-fails per invalid skill
    (logs a warning, doesn't raise) rather than breaking the whole tier."""
    return list_skills_in_dir(tier_dir)


def find_matching_skill_path(
    spec: dict, bu_id: str, org_id: str, usage_store: SkillUsageStore
) -> Optional[str]:
    """Tier precedence: BU -> org -> bundled, stop at the first tier with
    any match. Exact-set match on resource_types AND lifecycle_state ==
    'stable', read live from usage_store (never coarsely cached --
    staleness here has a correctness cost, docs/structured_match_rule_for_skills.md
    Part F0c). A 'provisional' or just-demoted skill matching on
    resource_types alone is not eligible. Ambiguity within the winning
    tier fails closed -- never falls through to a less-specific tier to
    break a tie. Cheap: only reads frontmatter, never does a full skill
    load."""
    normalized = normalize_resource_types(spec)
    for tier_dir in (f"workspaces/{bu_id}/skills", f"orgs/{org_id}/skills", "skills"):
        frontmatters = load_skills_in_tier(tier_dir)
        matching_ids = [
            skill_id
            for skill_id, fm in frontmatters.items()
            if set(fm.metadata.get("resource_types", [])) == normalized
            and usage_store.get_lifecycle_state(f"{tier_dir}/{skill_id}") == "stable"
        ]
        if len(matching_ids) == 1:
            return f"{tier_dir}/{matching_ids[0]}"
        if matching_ids:
            return None  # ambiguous -- fails closed, zero full loads spent
    return None


def resolve_skill_candidates(
    spec: dict, bu_id: str, org_id: str, usage_store: SkillUsageStore
) -> list[tuple[str, Skill]]:
    """Full resolution: find_matching_skill_path() plus one full
    load_skill_from_dir() call for the winner only -- never walks the
    tier directories twice for the same request. Returns a
    (skill_path, Skill) pair in a single-item list, or [] on no/ambiguous/
    not-yet-trusted match, matching the shape
    docs/structured_match_rule_for_skills.md describes."""
    skill_path = find_matching_skill_path(spec, bu_id, org_id, usage_store)
    if skill_path is None:
        return []
    return [(skill_path, load_skill_from_dir(skill_path))]
