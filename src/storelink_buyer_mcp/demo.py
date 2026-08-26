"""Terminal demonstration of the requested buyer workflow."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastmcp import Client

from .server import mcp


def show(step: str, value: Any) -> None:
    print(f"\n{step}")
    print(json.dumps(value, indent=2, ensure_ascii=False))


async def run_demo() -> None:
    request = {
        "sku": "8847291",
        "store_ids": [47, 102],
        "idempotency_key": "demo-madeta-8847291-47-102-v1",
    }
    show("STEP 1 — Buyer request translated to MCP arguments", request)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool = next(tool for tool in tools if tool.name == "replenish_store_stock")
        show("STEP 2 — Agent-selected tool and input schema", {
            "name": tool.name, "description": tool.description, "inputSchema": tool.inputSchema
        })

        result = await client.call_tool("replenish_store_stock", request)
        show("STEP 3 — Structured StoreLink evidence, decisions, and write result", result.data)

        buyer_audit = await client.read_resource("audit://buyer/recent")
        show("STEP 4 — Buyer audit view", json.loads(buyer_audit[0].text))

        technical_trace = await client.read_resource("audit://technical/recent")
        show("STEP 5 — FDE technical trace view", json.loads(technical_trace[0].text))

        retry = await client.call_tool("replenish_store_stock", request)
        show("STEP 6 — Safe retry with the same idempotency key", retry.data["summary"])


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
