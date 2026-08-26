"""Step 3 — observability for two readers.

The FDE needs a correlated, timed trace of what the server did upstream;
the buyer needs plain language describing what was done on their behalf.
"""

import json

import pytest
from fastmcp import Client

from storelink_buyer_mcp.server import mcp
from storelink_buyer_mcp.service import BuyerError


def _events(audit, operation_id):
    return [e for e in audit.technical_events if e.get("operation_id") == operation_id]


def test_s3_1_one_operation_id_ties_the_whole_run_together(service, audit):
    result = service.replenish_store_stock("8847291", [47, 102], "s3-1-key")
    events = _events(audit, result["operation_id"])
    names = [e["event"] for e in events]

    assert names[0] == "workflow.started"
    assert names[-1] == "workflow.completed"
    assert names.count("business_rule.evaluated") == 2
    assert "storelink.write.completed" in names
    # Upstream requests traced by the client layer carry the same id.
    assert any(e["event"] == "storelink_request" for e in events)
    # Milestones appear in causal order.
    assert names.index("workflow.started") < names.index("business_rule.evaluated")
    assert names.index("business_rule.evaluated") < names.index("storelink.write.completed")
    assert names.index("storelink.write.completed") < names.index("workflow.completed")


def test_s3_2_timings_and_dependencies_are_recorded(service, audit):
    result = service.replenish_store_stock("8847291", [47], "s3-2-key")
    events = _events(audit, result["operation_id"])
    reads = [e for e in events if e["event"] == "storelink.read.completed"]
    assert reads and all(
        isinstance(e["latency_ms"], (int, float)) and e["dependency"] == "StoreLink"
        for e in reads
    )
    completed = next(e for e in events if e["event"] == "workflow.completed")
    assert isinstance(completed["duration_ms"], (int, float))
    requests = [e for e in events if e["event"] == "storelink_request"]
    assert requests and all("duration_ms" in e and "path" in e for e in requests)


def test_s3_3_buyer_record_reads_as_plain_language(service, audit):
    service.replenish_store_stock("8847291", [47, 102], "s3-3-key")
    record = audit.buyer_events[-1]
    assert record["product"]["name"] == "Madeta butter 250g"
    assert "6 units" in record["rule_applied"]
    assert "47" in record["plain_language_summary"]
    assert record["plain_language_summary"].startswith("Replenishment was placed")
    assert record["was_safe_retry"] is False


def test_s3_4_failures_are_visible_to_both_readers(service, audit):
    with pytest.raises(BuyerError):
        service.replenish_store_stock("1111111", [47], "s3-4-key")
    failed = next(e for e in audit.technical_events if e["event"] == "workflow.failed")
    assert failed["error_type"] == "BuyerError"
    buyer_record = audit.buyer_events[-1]
    assert buyer_record["status"] == "failed"
    assert buyer_record["operation_id"] == failed["operation_id"]
    assert buyer_record["plain_language_summary"]
    assert buyer_record["next_step"]


def test_s3_5_both_logs_are_durable_parseable_jsonl(service, audit, tmp_path):
    service.replenish_store_stock("8847291", [47, 102], "s3-5-key")
    for name in ("technical.jsonl", "buyer.jsonl"):
        lines = (tmp_path / name).read_text().strip().splitlines()
        assert lines, name
        for line in lines:
            json.loads(line)


@pytest.mark.asyncio
async def test_s3_6_audit_is_reachable_over_mcp_and_correlated(unique_key):
    async with Client(mcp) as client:
        result = await client.call_tool("replenish_store_stock", {
            "sku": "8847291", "store_ids": [47, 102], "idempotency_key": unique_key,
        })
        operation_id = result.data["operation_id"]
        buyer_view = json.loads((await client.read_resource("audit://buyer/recent"))[0].text)
        technical_view = json.loads(
            (await client.read_resource("audit://technical/recent"))[0].text
        )
    assert any(r.get("operation_id") == operation_id for r in buyer_view["records"])
    assert any(r.get("operation_id") == operation_id for r in technical_view["records"])


def test_s3_7_nothing_is_written_to_stdout(service, capsys):
    service.replenish_store_stock("8847291", [47, 102], "s3-7-key")
    captured = capsys.readouterr()
    assert captured.out == ""  # stdout belongs to the MCP stdio transport
    assert "workflow.completed" in captured.err
