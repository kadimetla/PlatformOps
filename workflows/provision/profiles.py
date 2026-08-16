"""Trusted profile registrations for the provision planning boundary."""
from dataclasses import dataclass
from pathlib import Path

from workflows.provision.topology import TopologySpec, load_topology

_PROFILE_ROOT = Path(__file__).resolve().parents[2] / "skills" / "provision-infra" / "profiles"


@dataclass(frozen=True)
class ProfileRegistration:
    profile_id: str
    provider: str
    version: str
    topology_path: Path

    def load_topology(self) -> TopologySpec:
        return load_topology(self.topology_path)


PROFILE_REGISTRY: dict[str, ProfileRegistration] = {
    "aws-static-web": ProfileRegistration(
        profile_id="aws-static-web",
        provider="aws",
        version="1",
        topology_path=_PROFILE_ROOT / "aws-static-web" / "topology.yaml",
    )
}


def resolve_profile(profile_id: str) -> ProfileRegistration:
    try:
        return PROFILE_REGISTRY[profile_id]
    except KeyError as exc:
        raise ValueError(f"unknown deployment profile {profile_id!r}") from exc
