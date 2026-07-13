"""Tests for SkillUsageRecord storage (docs/config_storage_backend.md;
openspec/changes/wire-plan-request-envelope/ task group 4).
"""
from gateway.schemas import SkillPromotionPolicy
from gateway.skill_usage_store import SkillUsageStore

SKILL_PATH = "workspaces/payments/skills/s3-skill"


def _store(tmp_path) -> SkillUsageStore:
    return SkillUsageStore(str(tmp_path / "skill_usage.sqlite"))


def _policy(**overrides) -> SkillPromotionPolicy:
    return SkillPromotionPolicy(org_id="acme", **overrides)


def test_no_usage_record_defaults_to_provisional_fail_closed(tmp_path):
    store = _store(tmp_path)
    assert store.get_lifecycle_state(SKILL_PATH) == "provisional"


def test_three_consecutive_successes_promote_to_stable(tmp_path):
    store = _store(tmp_path)
    policy = _policy()
    for _ in range(3):
        store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    assert store.get_lifecycle_state(SKILL_PATH) == "stable"


def test_two_consecutive_successes_do_not_yet_promote(tmp_path):
    store = _store(tmp_path)
    policy = _policy()
    for _ in range(2):
        store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    assert store.get_lifecycle_state(SKILL_PATH) == "provisional"


def test_five_consecutive_failures_demote_stable_back_to_provisional(tmp_path):
    store = _store(tmp_path)
    policy = _policy()
    for _ in range(3):
        store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    assert store.get_lifecycle_state(SKILL_PATH) == "stable"

    for _ in range(5):
        store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", False, policy)
    assert store.get_lifecycle_state(SKILL_PATH) == "provisional"


def test_a_single_failure_resets_consecutive_successes_to_zero(tmp_path):
    store = _store(tmp_path)
    policy = _policy()
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", False, policy)
    # need 3 more consecutive successes from here, not 1, to promote
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    assert store.get_lifecycle_state(SKILL_PATH) == "provisional"


def test_thresholds_are_policy_not_hardcoded(tmp_path):
    store = _store(tmp_path)
    lenient_policy = _policy(consecutive_success_limit=1)
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, lenient_policy)
    assert store.get_lifecycle_state(SKILL_PATH) == "stable"


def test_total_and_successful_use_counters_accumulate(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "skill_usage.sqlite")
    store = SkillUsageStore(db_path)
    policy = _policy()
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", False, policy)
    store.record_skill_usage(SKILL_PATH, "bu", "acme", "payments", True, policy)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT total_uses, successful_uses FROM skill_usage_records WHERE skill_path = ?",
            (SKILL_PATH,),
        ).fetchone()
    assert row == (3, 2)
