"""Agent-facing MCP surface."""

from fastmcp import FastMCP

from .service import BuyerService
from .storelink import StoreLinkClient
from .audit import AuditRecorder

mcp = FastMCP(
    "StoreLink Category Buyer",
    instructions="Use these workflows to review inventory, investigate exceptions, and replenish stock safely.",
)
audit = AuditRecorder()
client = StoreLinkClient(trace=lambda event, **fields: audit.technical({"event": event, **fields}))
service = BuyerService(client, audit)


@mcp.tool
def list_categories() -> dict:
    """List the StoreLink category IDs available to this buyer."""
    return service.list_categories()


@mcp.tool
def review_category(category_id: str) -> dict:
    """Review category inventory health and see which products need attention."""
    return service.review_category(category_id)


@mcp.tool
def replenish_store_stock(sku: str, store_ids: list[int], idempotency_key: str) -> dict:
    """Check on-hand against last-24h POS and replenish stores whose gap exceeds 6 units."""
    return service.replenish_store_stock(sku, store_ids, idempotency_key)


@mcp.tool
def plan_replenishment(category_id: str) -> dict:
    """Create a deterministic, non-binding replenishment proposal grouped by supplier."""
    return service.plan_replenishment(category_id)


@mcp.tool
def submit_replenishment(plan_id: str, idempotency_key: str) -> dict:
    """Submit an unchanged replenishment plan once; retries with the same key are safe."""
    return service.submit_replenishment(plan_id, idempotency_key)


@mcp.tool
def get_purchase_order(purchase_order_id: str) -> dict:
    """Check the current StoreLink status and lines for a submitted purchase order."""
    return service.get_purchase_order(purchase_order_id)


@mcp.resource("audit://buyer/recent")
def recent_buyer_audit() -> dict:
    """Recent plain-language records of actions taken on a buyer's behalf."""
    return service.audit.recent("buyer")


@mcp.resource("audit://technical/recent")
def recent_technical_traces() -> dict:
    """Recent correlated diagnostic events for support engineers."""
    return service.audit.recent("technical")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
