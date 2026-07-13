"""SkillUsageRecord persistence -- docs/config_storage_backend.md's
resolution for the live, uncached lifecycle_state read
docs/structured_match_rule_for_skills.md Part F0c requires. A separate
class from BrokeredToolDispatcher (skill-trust bookkeeping is a
different concern from tool-intent dispatch), but the same physical
SQLite file -- one storage system, not two.
"""
import sqlite3

from .schemas import SkillPromotionPolicy


class SkillUsageStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_usage_records (
                    skill_path TEXT PRIMARY KEY,
                    tier TEXT NOT NULL,
                    org_id TEXT NOT NULL,
                    bu_id TEXT,
                    total_uses INTEGER NOT NULL DEFAULT 0,
                    successful_uses INTEGER NOT NULL DEFAULT 0,
                    consecutive_successes INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    lifecycle_state TEXT NOT NULL DEFAULT 'provisional',
                    last_used_at DATETIME,
                    last_failure_at DATETIME
                )
                """
            )

    def get_lifecycle_state(self, skill_path: str) -> str:
        """Live, uncached read -- no row means never proven, fail closed
        to 'provisional', matching SkillUsageRecord's own Pydantic
        default rather than treating absence as trust."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT lifecycle_state FROM skill_usage_records WHERE skill_path = ?",
                (skill_path,),
            ).fetchone()
        return row[0] if row else "provisional"

    def record_skill_usage(
        self,
        skill_path: str,
        tier: str,
        org_id: str,
        bu_id: str | None,
        success: bool,
        policy: SkillPromotionPolicy,
    ) -> None:
        """Atomic UPSERT -- thresholds applied in the same statement that
        updates counters, avoiding a lost-update race between two BUs
        using the same org-tier skill concurrently. Demotion target is
        'provisional', not a new state (docs/skill_promotion_thresholds.md
        Part D)."""
        # New-row values (skill used for the first time): counters start
        # from this single use; lifecycle_state can already reach
        # 'stable' if consecutive_success_limit is 1, so it's computed
        # in Python for the insert path rather than hardcoded.
        new_consecutive_successes = 1 if success else 0
        new_consecutive_failures = 0 if success else 1
        new_lifecycle_state = (
            "stable" if new_consecutive_successes >= policy.consecutive_success_limit
            else "provisional"
        )

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO skill_usage_records
                    (skill_path, tier, org_id, bu_id, total_uses, successful_uses,
                     consecutive_successes, consecutive_failures,
                     last_used_at, last_failure_at, lifecycle_state)
                VALUES (
                    ?, ?, ?, ?, 1, ?,
                    ?, ?,
                    CURRENT_TIMESTAMP, CASE WHEN ? THEN NULL ELSE CURRENT_TIMESTAMP END,
                    ?
                )
                ON CONFLICT(skill_path) DO UPDATE SET
                    total_uses = total_uses + 1,
                    successful_uses = successful_uses + excluded.successful_uses,
                    consecutive_successes = CASE
                        WHEN ? THEN consecutive_successes + 1 ELSE 0 END,
                    consecutive_failures = CASE
                        WHEN ? THEN 0 ELSE consecutive_failures + 1 END,
                    last_used_at = CURRENT_TIMESTAMP,
                    last_failure_at = CASE WHEN ? THEN last_failure_at ELSE CURRENT_TIMESTAMP END,
                    lifecycle_state = CASE
                        WHEN (CASE WHEN ? THEN consecutive_successes + 1 ELSE 0 END)
                            >= ? THEN 'stable'
                        WHEN (CASE WHEN ? THEN 0 ELSE consecutive_failures + 1 END)
                            >= ? THEN 'provisional'
                        ELSE lifecycle_state
                    END
                """,
                (
                    # INSERT path
                    skill_path, tier, org_id, bu_id,
                    int(success),
                    new_consecutive_successes, new_consecutive_failures,
                    success,
                    new_lifecycle_state,
                    # UPDATE path
                    success, success, success,
                    success, policy.consecutive_success_limit,
                    success, policy.consecutive_failure_limit,
                ),
            )
