"""Reviewed provision topology contracts and deterministic validation.

Topology data describes planning units only. It cannot name Python imports,
credentials, approval nodes, or executors. Runtime code resolves unit IDs
through trusted registries after this validation succeeds.
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field

JsonValue = Any


class LiteralBinding(BaseModel):
    kind: Literal["literal"]
    value: JsonValue


class RequestBinding(BaseModel):
    kind: Literal["request"]
    field: str = Field(min_length=1)


class WorkspaceBinding(BaseModel):
    kind: Literal["workspace"]
    field: str = Field(min_length=1)


class UnitOutputRef(BaseModel):
    kind: Literal["unit_output"]
    unit_id: str = Field(min_length=1)
    output_name: str = Field(min_length=1)


InputValue = Union[LiteralBinding, RequestBinding, WorkspaceBinding, UnitOutputRef]


class UnitSpec(BaseModel):
    id: str = Field(min_length=1)
    uses: str = Field(min_length=1)
    inputs: dict[str, InputValue] = Field(default_factory=dict)


class EdgeSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from", min_length=1)
    target: str = Field(alias="to", min_length=1)


class TopologySpec(BaseModel):
    schema_version: Literal["1"]
    name: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    provider: Literal["aws", "azure", "gcp"]
    units: list[UnitSpec] = Field(min_length=1)
    edges: list[EdgeSpec] = Field(default_factory=list)


class ValidatedTopology(BaseModel):
    spec: TopologySpec
    root_ids: list[str]
    leaf_ids: list[str]
    predecessors_by_target: dict[str, list[str]]


class TopologyValidationError(ValueError):
    """Raised when a reviewed topology is malformed or out of registry scope."""


def load_topology(path: Path) -> TopologySpec:
    """Load YAML as data; paths are supplied by trusted profile metadata."""

    data = yaml.safe_load(path.read_text()) or {}
    return TopologySpec.model_validate(data)


def validate_topology(
    spec: TopologySpec,
    *,
    profile_id: str,
    provider: str,
    registered_units: set[str],
) -> ValidatedTopology:
    if spec.profile != profile_id:
        raise TopologyValidationError("topology profile does not match selected profile")
    if spec.provider != provider:
        raise TopologyValidationError("topology provider does not match workspace provider")

    by_id: dict[str, UnitSpec] = {}
    for unit in spec.units:
        if unit.id in by_id:
            raise TopologyValidationError(f"duplicate topology unit id {unit.id!r}")
        if unit.uses not in registered_units:
            raise TopologyValidationError(f"unknown topology unit {unit.uses!r}")
        by_id[unit.id] = unit

    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in spec.edges:
        if edge.source not in by_id or edge.target not in by_id:
            raise TopologyValidationError("topology edge references an unknown unit")
        if edge.source == edge.target:
            raise TopologyValidationError("topology cannot contain a self-edge")
        if edge.source in predecessors[edge.target]:
            raise TopologyValidationError("topology contains a duplicate edge")
        predecessors[edge.target].append(edge.source)
        successors[edge.source].append(edge.target)

    for unit in spec.units:
        for binding in unit.inputs.values():
            if isinstance(binding, UnitOutputRef) and binding.unit_id not in by_id:
                raise TopologyValidationError(
                    f"unit {unit.id!r} binds output from unknown unit {binding.unit_id!r}"
                )
            if isinstance(binding, UnitOutputRef) and binding.unit_id == unit.id:
                raise TopologyValidationError(
                    f"unit {unit.id!r} cannot bind its own output"
                )

    indegree = {unit_id: len(predecessors[unit_id]) for unit_id in by_id}
    queue = deque(unit_id for unit_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while queue:
        unit_id = queue.popleft()
        ordered.append(unit_id)
        for successor in successors[unit_id]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    if len(ordered) != len(by_id):
        raise TopologyValidationError("topology graph must be acyclic")

    return ValidatedTopology(
        spec=spec,
        root_ids=[unit_id for unit_id in by_id if not predecessors[unit_id]],
        leaf_ids=[unit_id for unit_id in by_id if not successors[unit_id]],
        predecessors_by_target=dict(predecessors),
    )
