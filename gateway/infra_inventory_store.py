"""InfraInventoryStore -- the discovery data layer's storage, opening
the same db_path BrokeredToolDispatcher uses (one storage system, not
many, docs/config_storage_backend.md's established principle).
openspec/changes/infra-inventory-discovery/tasks.md task 1.
"""
import sqlite3
from typing import Optional

from .schemas import InfraInventoryRecord

# Scoped to resource types this project's discovery mechanisms plausibly
# encounter (network/compute/identity/storage top examples per provider),
# not an exhaustive catalog of every cloud resource type -- task 1.4's
# explicit instruction. Extend as new discovered types show up.
PROVIDER_TYPE_TO_CATEGORY: dict[str, str] = {
    # network
    "AWS::EC2::VPC": "network",
    "AWS::EC2::Subnet": "network",
    "compute.googleapis.com/Network": "network",
    "compute.googleapis.com/Subnetwork": "network",
    "Microsoft.Network/virtualNetworks": "network",
    "Microsoft.Network/subnets": "network",
    # compute
    "AWS::EC2::Instance": "compute",
    "AWS::EKS::Cluster": "compute",
    "compute.googleapis.com/Instance": "compute",
    "container.googleapis.com/Cluster": "compute",
    "Microsoft.Compute/virtualMachines": "compute",
    "Microsoft.ContainerService/managedClusters": "compute",
    # identity
    "AWS::IAM::Role": "identity",
    "iam.googleapis.com/ServiceAccount": "identity",
    "Microsoft.Authorization/roleAssignments": "identity",
    # storage
    "AWS::S3::Bucket": "storage",
    "storage.googleapis.com/Bucket": "storage",
    "Microsoft.Storage/storageAccounts": "storage",
}


def classify_resource_category(resource_type: str) -> Optional[str]:
    """Coarse category for a provider-native resource_type, or None if
    unrecognized -- classification failure is not an error, it just
    means this record won't participate in category-based ordering."""
    return PROVIDER_TYPE_TO_CATEGORY.get(resource_type)


class InfraInventoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS infra_inventory (
                    org_id TEXT NOT NULL,
                    bu_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    resource_identifier TEXT NOT NULL,
                    resource_category TEXT,
                    layer TEXT,
                    discovered_at DATETIME NOT NULL,
                    provenance TEXT NOT NULL,
                    PRIMARY KEY (org_id, bu_id, resource_type, resource_identifier)
                )
                """
            )

    def lookup(
        self, org_id: str, bu_id: str, resource_type: str, resource_identifier: str
    ) -> Optional[InfraInventoryRecord]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT org_id, bu_id, resource_type, resource_identifier,
                          resource_category, layer, discovered_at, provenance
                   FROM infra_inventory
                   WHERE org_id = ? AND bu_id = ? AND resource_type = ?
                         AND resource_identifier = ?""",
                (org_id, bu_id, resource_type, resource_identifier),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return InfraInventoryRecord(
            org_id=row[0],
            bu_id=row[1],
            resource_type=row[2],
            resource_identifier=row[3],
            resource_category=row[4],
            layer=row[5],
            discovered_at=row[6],
            provenance=row[7],
        )

    def upsert(self, record: InfraInventoryRecord) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO infra_inventory
                   (org_id, bu_id, resource_type, resource_identifier,
                    resource_category, layer, discovered_at, provenance)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.org_id,
                    record.bu_id,
                    record.resource_type,
                    record.resource_identifier,
                    record.resource_category,
                    record.layer,
                    record.discovered_at.isoformat(),
                    record.provenance,
                ),
            )

