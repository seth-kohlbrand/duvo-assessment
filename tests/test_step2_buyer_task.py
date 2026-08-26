"""Step 2 — the pilot buyer task, end to end, plus write-path safety.

The prompt scenario: SKU 8847291 (Madeta butter 250g) at stores 47 and
102; check on-hand vs last-24h POS and replenish only where the gap
exceeds 6 units. Stub data: store 47 has 3 on hand / 12 sold (gap 9),
store 102 has 8 on hand / 12 sold (gap 4).
"""

import pytest
from fastmcp import Client

from storelink_buyer_mcp.server import mcp
from storelink_buyer_mcp.service import BuyerError
from storelink_buyer_mcp.storelink import StoreLinkError


@pytest.mark.asyncio
async def test_s2_1_buyer_task_orders_store_47_only(unique_key):
    async with Client(mcp) as client:
        result = await client.call_tool("replenish_store_stock", {
            "sku": "8847291", "store_ids": [47, 102], "idempotency_key": unique_key,
        })
        data = result.data
    decisions = {check["store_id"]: check for check in data["store_checks"]}
    assert decisions[47]["on_hand_units"] == 3
    assert decisions[47]["pos_units_last_24h"] == 12
    assert decisions[47]["gap_units"] == 9
    assert decisions[47]["decision"] == "replenish"
    assert decisions[102]["gap_units"] == 4
    assert decisions[102]["decision"] == "no_action"
    assert len(data["orders_created"]) == 1
    order = data["orders_created"][0]
    assert order["store_id"] == 47 and order["quantity_units"] == 9
    assert data["product_name"] == "Madeta butter 250g"
    assert data["summary"]["duplicate_request"] is False


@pytest.mark.asyncio
async def test_s2_2_result_carries_evidence_for_every_store(unique_key):
    async with Client(mcp) as client:
        result = await client.call_tool("replenish_store_stock", {
            "sku": "8847291", "store_ids": [47, 102], "idempotency_key": unique_key,
        })
    for check in result.data["store_checks"]:
        for field in ("store_id", "on_hand_units", "pos_units_last_24h",
                      "gap_units", "threshold_units", "decision", "reason"):
            assert field in check, field
        assert check["threshold_units"] == 6


def test_s2_3_created_order_is_retrievable_with_status(service, traced_client):
    result = service.replenish_store_stock("8847291", [47, 102], "s2-3-key")
    order_id = result["orders_created"][0]["replenishment_order_id"]
    fetched = traced_client.get_replenishment_order(47, order_id)
    assert fetched["status"] == "received"
    assert fetched["quantity_units"] == 9 and fetched["sku"] == "8847291"


@pytest.mark.asyncio
async def test_s2_4_category_plan_submit_status_flow(unique_key):
    async with Client(mcp) as client:
        plan = (await client.call_tool("plan_replenishment", {"category_id": "beverages"})).data
        submitted = (await client.call_tool("submit_replenishment", {
            "plan_id": plan["plan_id"], "idempotency_key": unique_key,
        })).data
        po_id = submitted["purchase_orders"][0]["purchase_order_id"]
        status = (await client.call_tool("get_purchase_order", {"purchase_order_id": po_id})).data
    assert status["status"] == "submitted"
    assert status["lines"][0]["quantity"] == 34


@pytest.mark.parametrize("sku,store_ids,idempotency_key", [
    ("bad-sku", [47], "k"),          # non-digit SKU
    ("", [47], "k"),                 # empty SKU
    ("8847291", [], "k"),            # no stores
    ("8847291", list(range(1, 52)), "k"),  # more than 50 stores
    ("8847291", [47, 47], "k"),      # duplicates
    ("8847291", [0], "k"),           # zero id
    ("8847291", [-1], "k"),          # negative id
    ("8847291", [True], "k"),        # boolean smuggled as int
    ("8847291", [47], ""),           # empty idempotency key
    ("8847291", [47], "x" * 101),    # oversized idempotency key
])
def test_w1_malformed_requests_rejected_with_zero_writes(
    service, stub_transport, sku, store_ids, idempotency_key
):
    with pytest.raises(BuyerError):
        service.replenish_store_stock(sku, store_ids, idempotency_key)
    assert stub_transport._orders == {}


def test_w2_retry_with_same_key_creates_no_second_order(service, stub_transport):
    first = service.replenish_store_stock("8847291", [47, 102], "w2-key")
    retry = service.replenish_store_stock("8847291", [47, 102], "w2-key")
    assert retry["summary"]["duplicate_request"] is True
    assert retry["orders_created"] == first["orders_created"]
    assert len(stub_transport._orders) == 1


def test_w3_key_reuse_with_different_payload_is_rejected(traced_client, stub_transport):
    traced_client.create_replenishment_order(47, "8847291", 9, "first", "w3-key")
    with pytest.raises(StoreLinkError, match="409"):
        traced_client.create_replenishment_order(47, "8847291", 20, "changed", "w3-key")
    assert len(stub_transport._orders) == 1


def test_w4_failure_on_any_store_means_no_partial_writes(service, stub_transport):
    # Store 47 qualifies for replenishment, but store 999 has no credential:
    # the whole request must fail before anything is written.
    with pytest.raises(BuyerError, match="store 999"):
        service.replenish_store_stock("8847291", [47, 999], "w4-key")
    assert stub_transport._orders == {}

    with pytest.raises(BuyerError, match="Unknown SKU"):
        service.replenish_store_stock("1111111", [47], "w4-key-2")
    assert stub_transport._orders == {}
