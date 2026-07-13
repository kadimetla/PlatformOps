"""The brokered tool dispatcher: the runtime enforcement point that closes
the gap described in docs/HARNESS_DESIGN.md's "PlatformOps runtime boundary
to build next" — mutating MCP calls stop being a direct agent capability and
become a ToolIntent that must match a real, valid ApprovalRecord before
anything is allowed to reach CCAPI or Terraform apply. Deny by default.
"""
import json
import sqlite3
from typing import Any, Dict

from .config_engine import ConfigLoader


class BrokeredToolDispatcher:
    def __init__(self, db_path: str, config_loader: ConfigLoader):
        self.db_path = db_path
        self.config = config_loader
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    plan_id TEXT,
                    org_id TEXT,
                    bu_id TEXT,
                    resource_type TEXT,
                    operation TEXT,
                    decision TEXT,
                    reason TEXT,
                    payload TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    plan_id TEXT PRIMARY KEY,
                    plan_hash TEXT,
                    agent_approved INTEGER,
                    human_approved INTEGER,
                    is_valid INTEGER
                )
                """
            )

    def evaluate_intent(self, intent: Dict[str, Any]) -> bool:
        plan_id = intent.get("plan_id")
        plan_hash = intent.get("plan_hash")
        org_id = intent.get("org_id")
        bu_id = intent.get("bu_id")
        resource_type = intent.get("resource_type")
        region = intent.get("region")

        bundle = self.config.bundles.get(f"{org_id}-{bu_id}")
        if not bundle:
            self._log_audit(intent, "DENY", f"No workspace bundle found for {org_id}-{bu_id}")
            return False

        if resource_type not in bundle.allowed_resource_types:
            self._log_audit(
                intent, "DENY", f"Resource type {resource_type} not in allow-list for BU {bu_id}"
            )
            return False

        if region != bundle.aws_region:
            self._log_audit(
                intent,
                "DENY",
                f"Target region {region} does not match allowed region {bundle.aws_region}",
            )
            return False

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT plan_hash, agent_approved, human_approved, is_valid FROM approvals WHERE plan_id = ?",
                (plan_id,),
            )
            row = cursor.fetchone()
            if not row:
                self._log_audit(intent, "DENY", f"No approval record found for plan {plan_id}")
                return False

            db_hash, agent_app, _human_app, is_valid = row
            if plan_hash != db_hash:
                self._log_audit(intent, "DENY", "Plan hash mismatch. Tampering suspected.")
                return False

            if not is_valid:
                self._log_audit(intent, "DENY", "Approval record has been invalidated or expired.")
                return False

            # For the sandbox demo, agent approval alone is sufficient. A
            # production review_policy (see docs/HARNESS_DESIGN.md) would
            # require human_approved too for higher-risk resource types.
            if not agent_app:
                self._log_audit(intent, "DENY", "Agent approval missing.")
                return False

        self._log_audit(intent, "ALLOW", "Verification successful.")
        return True

    def _log_audit(self, intent: Dict[str, Any], decision: str, reason: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO audit_logs
                   (plan_id, org_id, bu_id, resource_type, operation, decision, reason, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    intent.get("plan_id"),
                    intent.get("org_id"),
                    intent.get("bu_id"),
                    intent.get("resource_type"),
                    intent.get("operation"),
                    decision,
                    reason,
                    json.dumps(intent.get("payload")),
                ),
            )

    def record_approval(
        self, plan_id: str, plan_hash: str, agent_approved: bool, human_approved: bool = False
    ):
        """Insert/replace the approval row a ToolIntent will be checked against.
        Real usage: called by the workflow layer once security_agent (and, if
        required, a human reviewer) has approved a PlanRecord — never by the
        provisioning agent itself.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO approvals
                   (plan_id, plan_hash, agent_approved, human_approved, is_valid)
                   VALUES (?, ?, ?, ?, 1)""",
                (plan_id, plan_hash, int(agent_approved), int(human_approved)),
            )
