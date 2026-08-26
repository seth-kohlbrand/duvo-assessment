"""Step 1 — the agent-facing surface.

Pins which tools exist, that no business rule is a tool parameter, and
that return shapes carry the evidence an agent needs to explain itself.
"""

import pytest
from fastmcp import Client

from storelink_buyer_mcp.server import mcp
from storelink_buyer_mcp.service import BuyerError

EXPECTED_TOOLS = {
    "list_categories", "review_category", "replenish_store_stock",
    "plan_replenishment", "submit_replenishment", "get_purchase_order",
}

# Business-rule inputs the agent must never be able to set.
FORBIDDEN_PARAMETERS = {
    "threshold", "threshold_units", "gap", "gap_units", "quantity",
    "quantity_units", "unit_cost", "cover_days", "price", "lead_time_days",
}


@pytest.mark.asyncio
async def test_s1_1_exactly_the_intended_tools_with_descriptions():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOLS
        for tool in tools:
            assert tool.description and len(tool.description) > 20, tool.name


@pytest.mark.asyncio
async def test_s1_2_no_business_rule_is_a_tool_parameter():
    async with Client(mcp) as client:
        for tool in await client.list_tools():
            parameters = set(tool.inputSchema.get("properties", {}))
            leaked = parameters & FORBIDDEN_PARAMETERS
            assert not leaked, f"{tool.name} exposes business-rule inputs: {leaked}"


def test_s1_3_review_category_shape_supports_agent_reasoning(service):
    review = service.review_category("beverages")
    assert review["category_id"] == "beverages"
    assert review["item_count"] == len(review["items"])
    attention_ids = {item["product_id"] for item in review["items_needing_attention"]}
    all_ids = {item["product_id"] for item in review["items"]}
    assert attention_ids <= all_ids
    for item in review["items"]:
        for field in ("product_id", "on_hand", "on_order", "units_sold_28d",
                      "days_of_cover", "needs_reorder", "recommended_quantity"):
            assert field in item, field


def test_s1_4_reorder_math_is_computed_server_side(service):
    plan = service.plan_replenishment("beverages")
    lines = plan["orders"][0]["lines"]
    assert [line["product_id"] for line in lines] == ["coffee-1kg"]
    # 56 sold / 28 days * 21 cover days = 42 target, minus 8 on hand = 34
    assert lines[0]["quantity"] == 34
    assert plan["total_cost"] == 425.0
    review = service.review_category("beverages")
    tea = next(i for i in review["items"] if i["product_id"] == "tea-100")
    assert tea["needs_reorder"] is False and tea["recommended_quantity"] == 0


@pytest.mark.asyncio
async def test_s1_5_audit_views_are_published_as_resources():
    async with Client(mcp) as client:
        resources = await client.list_resources()
        assert {str(resource.uri) for resource in resources} >= {
            "audit://buyer/recent", "audit://technical/recent",
        }


@pytest.mark.parametrize("call,fragment", [
    (lambda s: s.review_category("unknown-cat"), "unknown-cat"),
    (lambda s: s.investigate_product("unknown-prod"), "unknown-prod"),
    (lambda s: s.submit_replenishment("RP-nonexistent", "key"), "plan_id"),
    (lambda s: s.get_purchase_order("PO-9999"), "PO-9999"),
])
def test_s1_6_unknown_identifiers_fail_safely_naming_the_identifier(service, call, fragment):
    with pytest.raises(BuyerError, match=fragment):
        call(service)
