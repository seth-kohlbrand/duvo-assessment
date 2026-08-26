"""Step 4 — secret loading, weekly rotation, missing credentials.

These tests use the production credential path (StoreKeyProvider reading
the environment or a keys directory), not the stub's self-consistent key
provider, so the rotation and missing-key stories are exercised for real.
"""

import json
import os

import pytest
from fastmcp import Client, FastMCP

from storelink_buyer_mcp.credentials import MissingStoreCredentialError, StoreKeyProvider
from storelink_buyer_mcp.server import mcp
from storelink_buyer_mcp.service import BuyerError, BuyerService
from storelink_buyer_mcp.storelink import StoreLinkAuthError, StoreLinkClient


class PublishNewKeyOnFirstRejection:
    """Wraps the stub transport to simulate Korral IT publishing the new
    weekly key to the secret source between our first attempt and the
    client's re-read — the 'key rotates while a request is in flight' case."""

    def __init__(self, inner, store_id, new_key):
        self._inner = inner
        self._store_id = store_id
        self._new_key = new_key

    def request(self, *args, **kwargs):
        try:
            return self._inner.request(*args, **kwargs)
        except StoreLinkAuthError:
            os.environ[f"KORRAL_STORE_KEY_{self._store_id}"] = self._new_key
            raise

    def __getattr__(self, name):
        return getattr(self._inner, name)


class CountingTransport:
    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        return self._inner.request(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_s4_1_env_keys_are_read_fresh_on_every_request(monkeypatch):
    provider = StoreKeyProvider()
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-33-key")
    assert provider.get_key(47) == "week-33-key"
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-34-key")
    assert provider.get_key(47) == "week-34-key"  # no restart, no cache


def test_s4_2_file_source_env_precedence_and_empty_values(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    (keys_dir / "store_47.key").write_text("file-key-47\n")
    (keys_dir / "store_9.key").write_text("   \n")  # whitespace = not provisioned
    monkeypatch.setenv("KORRAL_STORE_KEYS_DIR", str(keys_dir))
    monkeypatch.delenv("KORRAL_STORE_KEY_47", raising=False)
    provider = StoreKeyProvider()

    assert provider.get_key(47) == "file-key-47"
    assert 47 in provider.available_store_ids()
    assert 9 not in provider.available_store_ids()
    with pytest.raises(MissingStoreCredentialError):
        provider.get_key(9)
    # A mounted file is the fallback; the environment variable wins.
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "env-key-47")
    assert provider.get_key(47) == "env-key-47"


def test_s4_3_rotation_mid_flight_retries_once_and_succeeds(
    stub_transport, audit, env_keys, monkeypatch
):
    # StoreLink already rotated to the week-34 key; our env still has week-33.
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-33-key")
    stub_transport.rotate_key(47, "week-34-key")
    transport = PublishNewKeyOnFirstRejection(stub_transport, 47, "week-34-key")
    client = StoreLinkClient(
        transport, StoreKeyProvider(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    service = BuyerService(client, audit)

    result = service.replenish_store_stock("8847291", [47], "s4-3-key")

    assert result["summary"]["stores_replenished"] == 1
    assert len(stub_transport._orders) == 1  # exactly one write despite the retry
    requests = [e for e in audit.technical_events if e["event"] == "storelink_request"]
    assert any(e["status"] == "auth_rejected" for e in requests)
    assert any(e.get("retried_after_rotation") is True for e in requests)


def test_s4_4_rotation_with_stale_source_fails_informatively_with_no_write(
    stub_transport, audit, env_keys, monkeypatch
):
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-33-key")
    stub_transport.rotate_key(47, "week-34-key")  # source never catches up
    client = StoreLinkClient(
        transport := CountingTransport(stub_transport), StoreKeyProvider(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    service = BuyerService(client, audit)

    with pytest.raises(StoreLinkAuthError) as failure:
        service.replenish_store_stock("8847291", [47], "s4-4-key")

    message = str(failure.value)
    assert "store 47" in message
    assert "unchanged" in message
    assert "Nothing was changed in StoreLink" in message
    assert "Korral IT" in message
    assert stub_transport._orders == {}
    assert transport.calls == 1  # exactly one attempt, no blind retry loop


def test_s4_5_missing_store_credential_fails_before_any_storelink_call(
    stub_transport, audit, env_keys
):
    transport = CountingTransport(stub_transport)
    client = StoreLinkClient(
        transport, StoreKeyProvider(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    service = BuyerService(client, audit)

    with pytest.raises(BuyerError) as failure:
        service.replenish_store_stock("8847291", [999], "s4-5-key")

    message = str(failure.value)
    assert "store 999" in message
    assert "47" in message and "102" in message  # tells the agent what IS available
    assert "Korral IT" in message
    assert transport.calls == 0
    assert stub_transport._orders == {}


def test_s4_6_traces_carry_fingerprints_never_key_material(
    stub_transport, audit, env_keys, tmp_path
):
    client = StoreLinkClient(
        stub_transport, StoreKeyProvider(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    BuyerService(client, audit).replenish_store_stock("8847291", [47, 102], "s4-6-key")

    requests = [e for e in audit.technical_events if e["event"] == "storelink_request"]
    assert requests
    for event in requests:
        fingerprint = event["key_fingerprint"]
        assert len(fingerprint) == 8 and int(fingerprint, 16) >= 0
    everything = json.dumps(audit.technical_events + audit.buyer_events)
    everything += (tmp_path / "technical.jsonl").read_text()
    assert "stub-key-47" not in everything
    assert "stub-key-102" not in everything


@pytest.mark.asyncio
async def test_s4_7a_missing_credential_error_reaches_the_agent_verbatim(unique_key):
    async with Client(mcp) as client:
        with pytest.raises(Exception) as failure:
            await client.call_tool("replenish_store_stock", {
                "sku": "8847291", "store_ids": [999], "idempotency_key": unique_key,
            })
    message = str(failure.value)
    assert "store 999" in message and "Korral IT" in message


@pytest.mark.asyncio
async def test_s4_7b_stale_rotation_error_reaches_the_agent_verbatim(
    stub_transport, audit, env_keys, monkeypatch
):
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "week-33-key")
    stub_transport.rotate_key(47, "week-34-key")
    storelink_client = StoreLinkClient(stub_transport, StoreKeyProvider())
    service = BuyerService(storelink_client, audit)

    boundary = FastMCP("boundary-test")

    @boundary.tool
    def replenish_store_stock(sku: str, store_ids: list[int], idempotency_key: str) -> dict:
        return service.replenish_store_stock(sku, store_ids, idempotency_key)

    async with Client(boundary) as client:
        with pytest.raises(Exception) as failure:
            await client.call_tool("replenish_store_stock", {
                "sku": "8847291", "store_ids": [47], "idempotency_key": unique(),
            })
    message = str(failure.value)
    assert "Korral IT" in message and "week-33-key" not in message


def unique():
    import uuid

    return f"s4-7b-{uuid.uuid4().hex[:8]}"
