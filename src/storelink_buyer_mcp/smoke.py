"""Interactive, human-reviewable smoke suite."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from fastmcp import Client

from .audit import AuditRecorder
from .server import mcp
from .service import BuyerService
from .storelink import StoreLinkClient, StubTransport


class SmokeFailure(RuntimeError):
    pass


def display(title: str, value: Any) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def pause(enabled: bool) -> None:
    if enabled:
        input("\nReview the output above, then press Enter to continue... ")


async def run(interactive: bool) -> None:
    request = {
        "sku": "8847291", "store_ids": [47, 102],
        "idempotency_key": "manual-smoke-madeta-v1",
    }

    async with Client(mcp) as client:
        tools = await client.list_tools()
        schemas = {tool.name: tool.inputSchema for tool in tools}
        serialized_schemas = json.dumps(schemas).lower()
        forbidden = [name for name in ("api_key", "credential", "password", "korral_store_key") if name in serialized_schemas]
        display("1. MCP surface — inspect tool arguments", {
            "tools": sorted(schemas), "replenish_store_stock_schema": schemas["replenish_store_stock"],
            "credential_parameters_found": forbidden, "check": "PASS" if not forbidden else "FAIL",
        })
        require(not forbidden, "A credential-like MCP parameter was exposed")
        pause(interactive)

        result = (await client.call_tool("replenish_store_stock", request)).data
        display("2. Authorized buyer workflow — inspect evidence and write", result)
        require(result["store_checks"][0]["gap_units"] == 9, "Store 47 gap should be 9")
        require(result["store_checks"][1]["gap_units"] == 4, "Store 102 gap should be 4")
        require([order["store_id"] for order in result["orders_created"]] == [47], "Only store 47 should receive an order")
        pause(interactive)

        buyer = json.loads((await client.read_resource("audit://buyer/recent"))[0].text)
        technical = json.loads((await client.read_resource("audit://technical/recent"))[0].text)
        operation_id = result["operation_id"]
        display("3A. Buyer audit — inspect plain-language accountability", buyer["records"][-1])
        display("3B. FDE trace — inspect correlated technical events", {
            "operation_id": operation_id,
            "records": [row for row in technical["records"] if row.get("operation_id") == operation_id],
        })
        require(buyer["records"][-1]["operation_id"] == operation_id, "Buyer audit is not correlated")
        pause(interactive)

        retry = (await client.call_tool("replenish_store_stock", request)).data
        display("4. Idempotent retry — inspect duplicate protection", retry["summary"])
        require(retry["summary"]["duplicate_request"] is True, "Retry was not deduplicated")
        pause(interactive)

        try:
            await client.call_tool("replenish_store_stock", {
                "sku": "8847291", "store_ids": [999], "idempotency_key": "manual-missing-store",
            })
            raise SmokeFailure("Uncredentialed store request unexpectedly succeeded")
        except SmokeFailure:
            raise
        except Exception as exc:
            missing_error = str(exc)
        buyer_after_failure = json.loads((await client.read_resource("audit://buyer/recent"))[0].text)["records"][-1]
        display("5. Missing store credential — inspect safe failure and audit", {
            "agent_error": missing_error, "buyer_audit": buyer_after_failure,
        })
        require("store 999" in missing_error and buyer_after_failure["status"] == "failed", "Missing-store failure was not informative and audited")
        require(buyer_after_failure["orders_created"] == [], "Missing-store failure created an order")
        pause(interactive)

    await rotation_scenarios(interactive)
    print("\nMANUAL SMOKE SUITE PASSED — all automated invariants held. Review the displayed evidence before sign-off.")


async def rotation_scenarios(interactive: bool) -> None:
    old_key = "SMOKE_CANARY_OLD_KEY_47"
    new_key = "SMOKE_CANARY_NEW_KEY_47"

    class RotatingKeys:
        calls = 0

        def available_store_ids(self):
            return [47]

        def get_key(self, store_id):
            self.calls += 1
            return old_key if self.calls == 1 else new_key

    transport = StubTransport()
    transport.rotate_key(47, new_key)
    audit = AuditRecorder()
    client = StoreLinkClient(transport, RotatingKeys(), trace=lambda event, **fields: audit.technical({"event": event, **fields}))
    result = BuyerService(client, audit).replenish_store_stock("8847291", [47], "manual-rotation-success")
    auth_events = [row for row in audit.technical_events if row["event"] == "storelink_request"]
    serialized = json.dumps({"result": result, "technical": audit.technical_events, "buyer": audit.buyer_events})
    display("6. Mid-flight key rotation — inspect bounded recovery", {
        "operation_id": result["operation_id"], "auth_events": auth_events,
        "raw_canary_visible": old_key in serialized or new_key in serialized,
    })
    require(any(row["status"] == "auth_rejected" for row in auth_events), "Initial rotated key was not rejected")
    require(any(row.get("retried_after_rotation") is True for row in auth_events), "Fresh key was not retried")
    require(old_key not in serialized and new_key not in serialized, "A raw key leaked into a surface")
    pause(interactive)

    class StaleKeys:
        def available_store_ids(self):
            return [47]

        def get_key(self, store_id):
            return old_key

    stale_transport = StubTransport()
    stale_transport.rotate_key(47, new_key)
    stale_audit = AuditRecorder()
    stale_client = StoreLinkClient(stale_transport, StaleKeys(), trace=lambda event, **fields: stale_audit.technical({"event": event, **fields}))
    try:
        BuyerService(stale_client, stale_audit).replenish_store_stock("8847291", [47], "manual-rotation-failure")
        raise SmokeFailure("Stale credential unexpectedly succeeded")
    except SmokeFailure:
        raise
    except Exception as exc:
        safe_error = str(exc)
    serialized_failure = json.dumps(stale_audit.technical_events + stale_audit.buyer_events) + safe_error
    display("7. Stale secret source — inspect zero-write failure", {
        "error": safe_error, "orders_in_storelink": len(stale_transport._orders),
        "buyer_audit": stale_audit.buyer_events[-1],
        "raw_canary_visible": old_key in serialized_failure or new_key in serialized_failure,
    })
    require(stale_transport._orders == {}, "Authentication failure produced a write")
    require(stale_audit.buyer_events[-1]["status"] == "failed", "Authentication failure was not audited")
    require(old_key not in serialized_failure and new_key not in serialized_failure, "A raw key leaked during failure")
    pause(interactive)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StoreLink manual smoke suite")
    parser.add_argument("--no-pause", action="store_true", help="Run all scenarios without waiting for Enter")
    args = parser.parse_args()
    asyncio.run(run(interactive=not args.no_pause))


if __name__ == "__main__":
    main()
