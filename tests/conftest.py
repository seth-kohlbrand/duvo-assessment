"""Shared fixtures for the step-organized test plan.

Imports inside fixtures are deliberate: it lets the host (Python 3.9,
no fastmcp) collect and run tests/test_step5_container.py, which only
shells out to Docker, while the full suite runs inside the image.
"""

import uuid

import pytest


@pytest.fixture
def stub_transport():
    from storelink_buyer_mcp.storelink import StubTransport

    return StubTransport()


@pytest.fixture
def audit(tmp_path, monkeypatch):
    from storelink_buyer_mcp.audit import AuditRecorder

    monkeypatch.setenv("STORELINK_AUDIT_DIR", str(tmp_path))
    return AuditRecorder()


@pytest.fixture
def traced_client(stub_transport, audit):
    """Client wired exactly like server.py: stub keys, trace into the audit."""
    from storelink_buyer_mcp.storelink import StoreLinkClient

    return StoreLinkClient(
        stub_transport,
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )


@pytest.fixture
def service(traced_client, audit):
    from storelink_buyer_mcp.service import BuyerService

    return BuyerService(traced_client, audit)


@pytest.fixture
def env_keys(monkeypatch):
    """Real environment-variable credentials matching the stub's current keys."""
    monkeypatch.setenv("KORRAL_STORE_KEY_47", "stub-key-47")
    monkeypatch.setenv("KORRAL_STORE_KEY_102", "stub-key-102")


@pytest.fixture
def env_service(stub_transport, audit, env_keys):
    """Service whose client reads keys from the environment (StoreKeyProvider),
    exercising the production credential path instead of the stub self-provider."""
    from storelink_buyer_mcp.credentials import StoreKeyProvider
    from storelink_buyer_mcp.service import BuyerService
    from storelink_buyer_mcp.storelink import StoreLinkClient

    client = StoreLinkClient(
        stub_transport,
        StoreKeyProvider(),
        trace=lambda event, **fields: audit.technical({"event": event, **fields}),
    )
    return BuyerService(client, audit)


@pytest.fixture
def unique_key():
    """Idempotency key that is unique per test run, for tests that go through
    the module-global server whose stub accumulates state within a session."""
    return f"test-{uuid.uuid4().hex[:12]}"
