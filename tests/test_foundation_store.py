"""openspec/changes/provision-kubernetes-cluster/tasks.md task 3.4."""
from gateway.foundation_store import FoundationStore
from gateway.schemas import FoundationRecord


def _record(**overrides) -> FoundationRecord:
    base = dict(
        foundation_id="fnd-1",
        org_id="acme",
        bu_id="payments",
        cloud_provider="aws",
        resource_type="AWS::EKS::Cluster",
        resource_identifier="payments-cluster",
        approved_plan_id="plan-1",
    )
    base.update(overrides)
    return FoundationRecord(**base)


def test_write_then_read_returns_the_record(tmp_path):
    store = FoundationStore(str(tmp_path / "foundation.sqlite"))
    store.record_foundation(_record())

    found = store.get_foundation("fnd-1")
    assert found is not None
    assert found.cloud_provider == "aws"
    assert found.resource_identifier == "payments-cluster"


def test_compute_paradigm_and_layer_default_to_kubernetes_and_compute(tmp_path):
    store = FoundationStore(str(tmp_path / "foundation.sqlite"))
    store.record_foundation(_record())

    found = store.get_foundation("fnd-1")
    assert found.compute_paradigm == "kubernetes"
    assert found.layer == "compute"


def test_lookup_returns_none_when_no_record_exists(tmp_path):
    store = FoundationStore(str(tmp_path / "foundation.sqlite"))
    assert store.get_foundation("does-not-exist") is None


def test_gcp_and_azure_providers_round_trip(tmp_path):
    store = FoundationStore(str(tmp_path / "foundation.sqlite"))
    store.record_foundation(_record(
        foundation_id="fnd-gcp", cloud_provider="gcp",
        resource_type="gke_cluster", resource_identifier="payments-gke",
    ))
    store.record_foundation(_record(
        foundation_id="fnd-azure", cloud_provider="azure",
        resource_type="azure_aks_cluster", resource_identifier="payments-aks",
    ))

    assert store.get_foundation("fnd-gcp").cloud_provider == "gcp"
    assert store.get_foundation("fnd-azure").cloud_provider == "azure"
