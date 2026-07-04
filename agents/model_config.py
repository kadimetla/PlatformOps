"""Loads per-role model identifiers from config/models.yaml so no agent
hardcodes a model string. See docs/HARNESS_DESIGN.md for the design this
is one real, working piece of.
"""
import os

import yaml

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")


def get_model(role: str) -> str:
    """Return the configured model identifier for an agent role
    (routing, execution, review, orchestration)."""
    with open(_CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    if role not in config:
        raise KeyError(f"No model configured for role '{role}' in {_CONFIG_PATH}")
    return config[role]["model"]
