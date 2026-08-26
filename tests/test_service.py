import pytest
import json

from storelink_buyer_mcp.audit import AuditRecorder
from storelink_buyer_mcp.credentials import StoreKeyProvider, MissingStoreCredentialError
from storelink_buyer_mcp.service import BuyerError, BuyerService
from storelink_buyer_mcp.storelink import StoreLinkClient, StubTransport


@pytest.fixture
def service():
    return BuyerService(StoreLinkClient())


def test_full_buyer_flow_and_idempotency(service):
    review = service.review_category("beverages")
    assert [item["product_id"] for item in review["items_needing_attention"]] == ["coffee-1kg"]

    plan = service.plan_replenishment("beverages")
    assert plan["orders"][0]["lines"][0]["quantity"] == 34
    assert plan["total_cost"] == 425.0

    first = service.submit_replenishment(plan["plan_id"], "buyer-run-001")
    retry = service.submit_replenishment(plan["plan_id"], "buyer-run-001")
    assert first["duplicate_request"] is False
    assert retry["duplicate_request"] is True
    assert retry["purchase_orders"] == first["purchase_orders"]

    po_id = first["purchase_orders"][0]["purchase_order_id"]
    assert service.get_purchase_order(po_id)["status"] == "submitted"


@pytest.mark.parametrize("operation", [
    lambda service: service.review_category("unknown"),
    lambda service: service.submit_replenishment("unknown", "key"),
    lambda service: service.get_purchase_order("unknown"),
])
def test_unknown_identifiers_are_rejected(service, operation):
    with pytest.raises(BuyerError):
        operation(service)


def test_empty_idempotency_key_is_rejected(service):
    plan = service.plan_replenishment("beverages")
    with pytest.raises(BuyerError):
        service.submit_replenishment(plan["plan_id"], "")


def test_store_replenishment_uses_fixed_rule_and_is_idempotent(service):
    first = service.replenish_store_stock("8847291", [47, 102], "store-demo-1")
    assert first["store_checks"][0]["gap_units"] == 9
    assert first["store_checks"][0]["decision"] == "replenish"
    assert first["store_checks"][1]["gap_units"] == 4
    assert first["store_checks"][1]["decision"] == "no_action"
    assert first["orders_created"][0]["store_id"] == 47
    assert first["orders_created"][0]["quantity_units"] == 9

    retry = service.replenish_store_stock("8847291", [47, 102], "store-demo-1")
    assert retry["summary"]["duplicate_request"] is True
    assert retry["orders_created"] == first["orders_created"]


@pytest.mark.parametrize("sku,store_ids", [
    ("bad-sku", [47]), ("8847291", []), ("8847291", [47, 47]),
    ("8847291", [-1]), ("8847291", [999]),
])
def test_store_replenishment_rejects_malformed_or_unknown_inputs(service, sku, store_ids):
    with pytest.raises(BuyerError):
        service.replenish_store_stock(sku, store_ids, "key")


def test_observability_links_technical_and_buyer_views_without_raw_key(tmp_path, monkeypatch):
    monkeypatch.setenv("STORELINK_AUDIT_DIR", str(tmp_path))
    audit = AuditRecorder()
    observed_service = BuyerService(StoreLinkClient(), audit)
    result = observed_service.replenish_store_stock("8847291", [47, 102], "secret-retry-key")

    operation_id = result["operation_id"]
    assert {record["operation_id"] for record in audit.buyer_events} == {operation_id}
    assert {record["operation_id"] for record in audit.technical_events} == {operation_id}
    assert audit.buyer_events[0]["plain_language_summary"].startswith("Replenishment was placed")
    assert any(record["event"] == "storelink.write.completed" for record in audit.technical_events)
    assert "secret-retry-key" not in json.dumps(audit.technical_events + audit.buyer_events)
    assert (tmp_path / "technical.jsonl").is_file()
    assert (tmp_path / "buyer.jsonl").is_file()


def test_key_rotation_is_reloaded_once_and_correlated_without_exposing_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("STORELINK_AUDIT_DIR", str(tmp_path))
    transport = StubTransport()
    transport.rotate_key(47, "new-weekly-key-47")

    class RotatingKeys:
        calls = 0

        def available_store_ids(self):
            return [47, 102]

        def get_key(self, store_id):
            if store_id == 102:
                return "stub-key-102"
            self.calls += 1
            return "old-weekly-key-47" if self.calls == 1 else "new-weekly-key-47"

    audit = AuditRecorder()
    client = StoreLinkClient(
        transport, RotatingKeys(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    rotating_service = BuyerService(client, audit)
    result = rotating_service.replenish_store_stock("8847291", [47], "rotation-request")

    requests = [event for event in audit.technical_events if event["event"] == "storelink_request"]
    assert any(event["status"] == "auth_rejected" for event in requests)
    assert any(event.get("retried_after_rotation") is True for event in requests)
    assert {event["operation_id"] for event in requests} == {result["operation_id"]}
    serialized = json.dumps(audit.technical_events + audit.buyer_events)
    assert "old-weekly-key-47" not in serialized
    assert "new-weekly-key-47" not in serialized


def test_rotation_with_stale_secret_fails_once_audits_and_makes_no_write():
    transport = StubTransport()
    transport.rotate_key(47, "storelink-new-key")

    class StaleKeys:
        def available_store_ids(self):
            return [47]

        def get_key(self, store_id):
            return "secret-source-still-old"

    audit = AuditRecorder()
    client = StoreLinkClient(
        transport, StaleKeys(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    stale_service = BuyerService(client, audit)

    with pytest.raises(Exception, match="rotation has likely happened"):
        stale_service.replenish_store_stock("8847291", [47], "stale-rotation-request")
    assert transport._orders == {}
    assert audit.buyer_events[-1]["status"] == "failed"
    assert audit.buyer_events[-1]["orders_created"] == []
    serialized = json.dumps(audit.technical_events + audit.buyer_events)
    assert "storelink-new-key" not in serialized
    assert "secret-source-still-old" not in serialized


def test_missing_store_credential_fails_before_storelink_and_creates_buyer_audit(service):
    with pytest.raises(BuyerError, match="No StoreLink credential is configured for store 999"):
        service.replenish_store_stock("8847291", [999], "missing-store-request")

    failure = service.audit.buyer_events[-1]
    assert failure["status"] == "failed"
    assert failure["orders_created"] == []
    assert "Korral IT" in failure["next_step"]
    assert "missing-store-request" not in json.dumps(failure)


def test_store_key_provider_reads_rotated_secret_without_restart(monkeypatch):
    provider = StoreKeyProvider()
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-one-key")
    assert provider.get_key(47) == "week-one-key"
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-two-key")
    assert provider.get_key(47) == "week-two-key"


def test_missing_store_key_error_lists_ids_without_values(monkeypatch):
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "do-not-expose-this")
    provider = StoreKeyProvider()
    with pytest.raises(MissingStoreCredentialError) as error:
        provider.get_key(999)
    assert "47" in str(error.value)
    assert "do-not-expose-this" not in str(error.value)


def test_canary_credential_never_reaches_results_errors_or_logs(tmp_path, monkeypatch, capsys):
    canary = "LEAK_TEST_SECRET_47_9f8d7c6b"
    monkeypatch.setenv("KORRAL_STORE_KEY_47", canary)
    monkeypatch.setenv("STORELINK_AUDIT_DIR", str(tmp_path))
    transport = StubTransport()
    transport.rotate_key(47, canary)
    audit = AuditRecorder()
    client = StoreLinkClient(
        transport, StoreKeyProvider(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    canary_service = BuyerService(client, audit)

    result = canary_service.replenish_store_stock("8847291", [47], "canary-success")
    success_surfaces = json.dumps(result) + json.dumps(audit.recent("technical")) + json.dumps(audit.recent("buyer"))
    success_surfaces += (tmp_path / "technical.jsonl").read_text()
    success_surfaces += (tmp_path / "buyer.jsonl").read_text()
    success_surfaces += capsys.readouterr().err
    assert canary not in success_surfaces

    transport.rotate_key(47, "StoreLink-has-a-newer-key")
    with pytest.raises(Exception) as failure:
        canary_service.replenish_store_stock("8847291", [47], "canary-failure")
    failure_surfaces = str(failure.value) + json.dumps(audit.recent("technical")) + json.dumps(audit.recent("buyer"))
    failure_surfaces += (tmp_path / "technical.jsonl").read_text()
    failure_surfaces += (tmp_path / "buyer.jsonl").read_text()
    failure_surfaces += capsys.readouterr().err
    assert canary not in failure_surfaces
