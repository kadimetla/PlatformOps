"""openspec/changes/provision-kubernetes-cluster/tasks.md task 3.4.
FoundationRecord/FoundationStore renamed to ResourceRecord/ResourceStore
(docs/composable_foundation_blueprints.md Parts G/M); blueprint_id
sketch settled as the required stack_id field.
"""
from gateway.resource_store import ResourceStore
from gateway.schemas import ResourceRecord


def _record(**overrides) -> ResourceRecord:
    base = dict(
        resource_id="res-1",
        stack_id="stack-1",
        org_id="acme",
        bu_id="payments",
        cloud_provider="aws",
        resource_type="AWS::EKS::Cluster",
        resource_identifier="payments-cluster",
        approved_plan_id="plan-1",
    )
    base.update(overrides)
    return ResourceRecord(**base)


def test_write_then_read_returns_the_record(tmp_path):
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    store.record_resource(_record())

    found = store.get_resource("res-1")
    assert found is not None
    assert found.cloud_provider == "aws"
    assert found.resource_identifier == "payments-cluster"
    assert found.stack_id == "stack-1"


def test_compute_paradigm_and_layer_default_to_kubernetes_and_compute(tmp_path):
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    store.record_resource(_record())

    found = store.get_resource("res-1")
    assert found.compute_paradigm == "kubernetes"
    assert found.layer == "compute"


def test_lookup_returns_none_when_no_record_exists(tmp_path):
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    assert store.get_resource("does-not-exist") is None


def test_gcp_and_azure_providers_round_trip(tmp_path):
    store = ResourceStore(str(tmp_path / "resources.sqlite"))
    store.record_resource(_record(
        resource_id="res-gcp", cloud_provider="gcp",
        resource_type="gke_cluster", resource_identifier="payments-gke",
    ))
    store.record_resource(_record(
        resource_id="res-azure", cloud_provider="azure",
        resource_type="azure_aks_cluster", resource_identifier="payments-aks",
    ))

    assert store.get_resource("res-gcp").cloud_provider == "gcp"
    assert store.get_resource("res-azure").cloud_provider == "azure"
