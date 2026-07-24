"""FoundationRecord persistence -- openspec/changes/provision-kubernetes-cluster.
A separate class from BrokeredToolDispatcher (foundation-tier resource
bookkeeping is a different concern from tool-intent dispatch), but the
same physical SQLite file -- one storage system, not two, matching
docs/config_storage_backend.md's established convention.
"""
import json
import sqlite3
from typing import Optional

from .schemas import FoundationRecord


class FoundationStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS foundation_records (
                    foundation_id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    bu_id TEXT NOT NULL,
                    cloud_provider TEXT NOT NULL,
                    compute_paradigm TEXT NOT NULL DEFAULT 'kubernetes',
                    layer TEXT NOT NULL DEFAULT 'compute',
                    resource_type TEXT NOT NULL,
                    resource_identifier TEXT NOT NULL,
                    approved_plan_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    provenance TEXT NOT NULL DEFAULT 'created',
                    discovered_capabilities TEXT NOT NULL DEFAULT '{}',
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def record_foundation(self, record: FoundationRecord) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO foundation_records
                   (foundation_id, org_id, bu_id, cloud_provider, compute_paradigm,
                    layer, resource_type, resource_identifier, approved_plan_id,
                    status, provenance, discovered_capabilities, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.foundation_id,
                    record.org_id,
                    record.bu_id,
                    record.cloud_provider,
                    record.compute_paradigm,
                    record.layer,
                    record.resource_type,
                    record.resource_identifier,
                    record.approved_plan_id,
                    record.status,
                    record.provenance,
                    json.dumps(record.discovered_capabilities),
                    record.created_at.isoformat(),
                ),
            )

    def get_foundation(self, foundation_id: str) -> Optional[FoundationRecord]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT foundation_id, org_id, bu_id, cloud_provider, compute_paradigm,
                          layer, resource_type, resource_identifier, approved_plan_id,
                          status, provenance, created_at
                   FROM foundation_records WHERE foundation_id = ?""",
                (foundation_id,),
            ).fetchone()
        if row is None:
            return None
        return FoundationRecord(
            foundation_id=row[0],
            org_id=row[1],
            bu_id=row[2],
            cloud_provider=row[3],
            compute_paradigm=row[4],
            layer=row[5],
            resource_type=row[6],
            resource_identifier=row[7],
            approved_plan_id=row[8],
            status=row[9],
            provenance=row[10],
            created_at=row[11],
        )
