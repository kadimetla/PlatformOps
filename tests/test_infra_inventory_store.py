"""openspec/changes/infra-inventory-discovery/tasks.md task 1.5."""
from gateway.infra_inventory_store import InfraInventoryStore, classify_resource_category
from gateway.schemas import InfraInventoryRecord
from gateway.tool_dispatcher import BrokeredToolDispatcher
from gateway.config_engine import ConfigLoader


def test_lookup_returns_none_when_no_record_exists(tmp_path):
    store = InfraInventoryStore(str(tmp_path / "inventory.sqlite"))
    assert store.lookup("acme", "payments", "AWS::S3::Bucket", "invoices-prod") is None


def test_upsert_then_lookup_returns_at_most_one_record(tmp_path):
    store = InfraInventoryStore(str(tmp_path / "inventory.sqlite"))
    store.upsert(
        InfraInventoryRecord(
            org_id="acme",
            bu_id="payments",
            resource_type="AWS::S3::Bucket",
            resource_identifier="invoices-prod",
            resource_category="storage",
            provenance="live_api",
        )
    )
    found = store.lookup("acme", "payments", "AWS::S3::Bucket", "invoices-prod")
    assert found is not None
    assert found.resource_identifier == "invoices-prod"
    assert found.resource_category == "storage"
    assert found.provenance == "live_api"


def test_upsert_is_idempotent_on_the_same_key(tmp_path):
    store = InfraInventoryStore(str(tmp_path / "inventory.sqlite"))
    key = dict(org_id="acme", bu_id="payments", resource_type="AWS::S3::Bucket", resource_identifier="invoices-prod")
    store.upsert(InfraInventoryRecord(**key, provenance="iac_state"))
    store.upsert(InfraInventoryRecord(**key, provenance="live_api"))  # re-discovered later
    found = store.lookup(**key)
    assert found.provenance == "live_api"  # the later write wins, not a duplicate row


def test_gcp_native_resource_type_round_trips_unchanged(tmp_path):
    store = InfraInventoryStore(str(tmp_path / "inventory.sqlite"))
    store.upsert(
        InfraInventoryRecord(
            org_id="acme",
            bu_id="payments",
            resource_type="compute.googleapis.com/Network",
            resource_identifier="prod-vpc",
            provenance="iac_state",
        )
    )
    found = store.lookup("acme", "payments", "compute.googleapis.com/Network", "prod-vpc")
    assert found.resource_type == "compute.googleapis.com/Network"  # not translated to CFN style


def test_classification_table_maps_each_providers_network_type_to_network_category():
    assert classify_resource_category("AWS::EC2::VPC") == "network"
    assert classify_resource_category("compute.googleapis.com/Network") == "network"
    assert classify_resource_category("Microsoft.Network/virtualNetworks") == "network"


def test_classification_returns_none_for_unrecognized_type():
    assert classify_resource_category("Some::Unknown::Type") is None


def test_inventory_and_dispatcher_tables_coexist_in_one_sqlite_file_without_conflict(tmp_path):
    db_path = str(tmp_path / "shared.sqlite")

    config_dir = tmp_path / "config"
    (config_dir / "workspace_bundles").mkdir(parents=True)
    (config_dir / "workspace_bundles" / "acme-payments.yaml").write_text(
        "bundle_id: acme-payments\naws_region: us-east-1\nallowed_resource_types:\n  - AWS::S3::Bucket\n"
    )
    (config_dir / "bindings.yaml").write_text(
        "bindings:\n  - agent_id: a1\n    org_id: acme\n    bu_id: payments\n    workspace_bundle_ref: acme-payments\n"
    )
    loader = ConfigLoader(str(config_dir))
    loader.load_and_validate()

    dispatcher = BrokeredToolDispatcher(db_path, loader)
    inventory = InfraInventoryStore(db_path)

    inventory.upsert(
        InfraInventoryRecord(
            org_id="acme",
            bu_id="payments",
            resource_type="AWS::S3::Bucket",
            resource_identifier="invoices-prod",
            provenance="live_api",
        )
    )

    assert inventory.lookup("acme", "payments", "AWS::S3::Bucket", "invoices-prod") is not None
    # dispatcher's own tables are still queryable in the same file
    dispatcher._log_audit({"plan_id": "p1"}, "DENY", "test")
