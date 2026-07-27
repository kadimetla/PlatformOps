"""ResourceRecord persistence -- openspec/changes/provision-kubernetes-cluster.
Renamed from FoundationStore/FoundationRecord (docs/composable_foundation_blueprints.md
Parts G/M -- "no more foundation/platform," matches Stack/Resource
terminology). A separate class from BrokeredToolDispatcher (resource
bookkeeping is a different concern from tool-intent dispatch), but the
same physical SQLite file -- one storage system, not two, matching
docs/config_storage_backend.md's established convention.
"""
import json
import sqlite3
from typing import Optional

from .schemas import ResourceRecord


class ResourceStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resource_records (
                    resource_id TEXT PRIMARY KEY,
                    stack_id TEXT NOT NULL,
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

    def record_resource(self, record: ResourceRecord) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO resource_records
                   (resource_id, stack_id, org_id, bu_id, cloud_provider, compute_paradigm,
                    layer, resource_type, resource_identifier, approved_plan_id,
                    status, provenance, discovered_capabilities, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.resource_id,
                    record.stack_id,
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

    def get_resource(self, resource_id: str) -> Optional[ResourceRecord]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT resource_id, stack_id, org_id, bu_id, cloud_provider, compute_paradigm,
                          layer, resource_type, resource_identifier, approved_plan_id,
                          status, provenance, created_at
                   FROM resource_records WHERE resource_id = ?""",
                (resource_id,),
            ).fetchone()
        if row is None:
            return None
        return ResourceRecord(
            resource_id=row[0],
            stack_id=row[1],
            org_id=row[2],
            bu_id=row[3],
            cloud_provider=row[4],
            compute_paradigm=row[5],
            layer=row[6],
            resource_type=row[7],
            resource_identifier=row[8],
            approved_plan_id=row[9],
            status=row[10],
            provenance=row[11],
            created_at=row[12],
        )
