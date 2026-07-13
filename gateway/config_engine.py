"""Loads and validates bindings + workspace bundles, failing closed on bad
config per docs/HARNESS_DESIGN.md's "Borrow: schema-validated, hot-reloadable
config" section. No binding is trusted until every reference it makes
resolves to a real, loaded WorkspaceBundle.
"""
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import ValidationError

from .schemas import WorkspaceBundle


class ConfigLoader:
    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self.bundles: Dict[str, WorkspaceBundle] = {}
        self.bindings: List[dict] = []

    def load_and_validate(self):
        self._load_workspace_bundles()
        self._load_bindings()
        self._validate_referential_integrity()
        self._validate_uniqueness()
        print(f"Config successfully loaded. Active Bundles: {list(self.bundles.keys())}")

    def _load_workspace_bundles(self):
        bundle_path = self.config_dir / "workspace_bundles"
        if not bundle_path.exists():
            raise FileNotFoundError(f"Missing workspace bundles directory at {bundle_path}")

        for f in sorted(bundle_path.glob("*.yaml")):
            with open(f) as stream:
                data = yaml.safe_load(stream)
            try:
                bundle = WorkspaceBundle(**data)
            except ValidationError as e:
                raise ValueError(f"Invalid config in bundle file {f.name}: {e}") from e
            self.bundles[bundle.bundle_id] = bundle

    def _load_bindings(self):
        bindings_file = self.config_dir / "bindings.yaml"
        if not bindings_file.exists():
            raise FileNotFoundError(f"Missing bindings file at {bindings_file}")

        with open(bindings_file) as stream:
            bindings_data = yaml.safe_load(stream)
        self.bindings = bindings_data.get("bindings", [])

    def _validate_referential_integrity(self):
        for binding in self.bindings:
            ref = binding.get("workspace_bundle_ref")
            if ref not in self.bundles:
                raise ValueError(
                    f"Binding {binding.get('agent_id')} references non-existent "
                    f"workspace bundle '{ref}'"
                )

    def _validate_uniqueness(self):
        """An agent_id may appear in multiple bindings (e.g. one BU reachable
        via Slack and a webhook) — what's forbidden is two DIFFERENT BUs
        sharing one agent_id, which would break OpenClaw-style isolation
        (see docs/HARNESS_DESIGN.md's binding validation rules)."""
        agent_id_to_bu: Dict[str, tuple] = {}
        for binding in self.bindings:
            agent_id = binding.get("agent_id")
            bu_key = (binding.get("org_id"), binding.get("bu_id"))
            if agent_id in agent_id_to_bu and agent_id_to_bu[agent_id] != bu_key:
                raise ValueError(
                    f"agent_id '{agent_id}' is bound to two different BUs: "
                    f"{agent_id_to_bu[agent_id]} and {bu_key} — every agent_id must "
                    "map to exactly one BU, never shared across BUs."
                )
            agent_id_to_bu[agent_id] = bu_key
