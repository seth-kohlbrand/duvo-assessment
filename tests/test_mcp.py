import pytest
from fastmcp import Client

from storelink_buyer_mcp.server import mcp


@pytest.mark.asyncio
async def test_tools_are_exposed_through_mcp():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {
            "list_categories", "review_category", "replenish_store_stock",
            "plan_replenishment", "submit_replenishment", "get_purchase_order",
        }
        result = await client.call_tool("review_category", {"category_id": "beverages"})
        assert result.data["category_id"] == "beverages"


@pytest.mark.asyncio
async def test_audit_views_are_mcp_resources():
    async with Client(mcp) as client:
        resources = await client.list_resources()
        assert {str(resource.uri) for resource in resources} >= {
            "audit://buyer/recent", "audit://technical/recent"
        }


@pytest.mark.asyncio
async def test_mcp_surface_has_no_credential_parameter():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        schemas = str([tool.inputSchema for tool in tools]).lower()
        for forbidden in ("api_key", "api-key", "credential", "password", "korral_store_key"):
            assert forbidden not in schemas
