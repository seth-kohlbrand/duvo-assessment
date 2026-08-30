# StoreLink Category Buyer MCP

A deliberately small FastMCP server that gives a Duvo agent the workflows needed to monitor a category and replenish stock. StoreLink is represented by an in-memory stub; the boundary is isolated in `storelink.py` so it can be replaced by an authenticated API client.

## Tool decisions

- `list_categories` provides discoverable valid IDs instead of making the agent guess.
- `review_category` is the buyer's starting view: inventory health plus a short attention list.
- `replenish_store_stock` handles an authorized store exception end to end: it fetches evidence, applies the fixed gap rule, and writes only required orders.
- `plan_replenishment` performs reorder calculations server-side and returns a reviewable, supplier-grouped proposal. The agent cannot tune business-rule inputs.
- `submit_replenishment` accepts a plan, not arbitrary PO lines. This separates review from the write and requires an idempotency key.
- `get_purchase_order` closes the loop after submission.

I intentionally did not expose generic StoreLink CRUD, raw stock adjustments, supplier administration, or configurable reorder formulas. Those expand permissions without helping this focused buyer workflow. The fixed 21-day cover rule is illustrative business logic and lives in the deterministic service layer.

## Run and test

These commands were exercised with Docker:

```bash
docker build -t storelink-buyer-mcp:exercise .
docker run --rm -i storelink-buyer-mcp:exercise
docker run --rm --entrypoint sh -v "$PWD:/workspace:ro" -w /workspace storelink-buyer-mcp:exercise -c "pip install -q 'pytest>=8,<9' 'pytest-asyncio>=0.24,<2' && PYTHONPATH=src pytest -q"
```

The server requires Python 3.10 or newer and uses stdio, suitable for an MCP client configuration. No StoreLink secret is needed for the stub. A real client should read its rotatable credential from the environment at request time.

## Per-store credentials and weekly rotation

StoreLink credentials are server configuration, never MCP tool parameters or tool output. `StoreKeyProvider` looks up a store's key in this order:

1. `KORRAL_STORE_KEY_<store_id>` environment variable, such as `KORRAL_STORE_KEY_47`.
2. `store_<store_id>.key` beneath `KORRAL_STORE_KEYS_DIR`, intended for a mounted secret volume updated by Korral IT.

The value is read for every StoreLink request and is never cached. This lets a mounted secret update take effect without restarting the MCP server. Keys are never logged; technical correlation uses only a short, non-reversible SHA-256 fingerprint.

If StoreLink rejects a key while a request is in flight, the client assumes a rotation may have landed between secret lookup and authentication. It reads the key source again and retries exactly once, and the technical trace records the rejection and whether the retry used a refreshed key. If the source is unchanged or the second attempt fails, the operation stops. No further StoreLink calls are attempted, no replenishment write is inferred as successful, and the error tells Korral IT that StoreLink and the secret source may be out of sync.

If an agent requests a store for which the server has no credential, validation fails before any StoreLink read or write. The agent receives the unavailable store ID and the IDs this server can access, but never a credential value. The buyer audit records a failed action with zero orders and directs the buyer to Korral IT; the technical trace records the same failure under its `operation_id`.

## Connect the server to an agent

The runnable demo is `scripts/agent_demo.sh`. It builds the server image,
generates an MCP config for your checkout, and drives a real agent
(Claude Code in headless mode) over stdio MCP through the pilot buyer
task — no bespoke driver script, the agent picks the tools itself:

```bash
scripts/agent_demo.sh
```

The agent discovers exactly the six tools and, given the pilot buyer task
for SKU 8847291 at stores 47 and 102, replenishes store 47 (gap 9 > 6,
order R47-0001 for 9 units), leaves store 102 alone (gap 4), and its
retry with the same idempotency key is deduplicated with zero extra
writes. The captured transcript, tool calls, and final answer land in
`demo_artifacts/`; `docs/AGENT_DEMO.md` walks through a captured run.
Requires `docker`, the `claude` CLI, and `jq`. The generated config block
(`demo_artifacts/mcp-config.json`, mirrored at `mcp-config.json` in the
repo root) works for any MCP client that speaks stdio.

## Run the buyer-request demo

After building the image, this prints every MCP step and its structured JSON output:

```bash
docker run --rm --entrypoint storelink-buyer-demo storelink-buyer-mcp:exercise
```

## Manual smoke suite

Build once, then run the interactive suite with stdin attached:

```bash
docker build -t storelink-buyer-mcp:exercise .
docker run --rm -i --entrypoint storelink-buyer-smoke storelink-buyer-mcp:exercise
```

The suite pauses after each scenario. Review the displayed JSON, then press Enter. It covers the MCP schema, buyer request, both audit views, safe retry, missing-store credentials, successful weekly-key rotation, stale-secret failure, zero-write guarantees, and canary-key redaction. The final line is `MANUAL SMOKE SUITE PASSED`; that means its invariants passed, but you should still review the evidence shown above it.

For CI-style execution without pauses:

```bash
docker run --rm --entrypoint storelink-buyer-smoke storelink-buyer-mcp:exercise --no-pause
```

## Observability and audit log

Every store-replenishment run receives an `operation_id`. That same ID appears in the tool result, the technical trace, and the buyer audit record, so support and business users can discuss the exact same action without translating between logging systems.

### FDE technical trace

Technical events are emitted as single-line JSON to stderr, preserving stdout for the MCP stdio protocol, and appended to `technical.jsonl`. They include:

- UTC timestamp, `operation_id`, workflow, event phase, and total duration.
- StoreLink dependency method, per-call latency, success/found state, and returned order IDs.
- Inputs useful for diagnosis: SKU, store IDs, on-hand, POS, computed gap, fixed threshold, and decision.
- Write count, duplicate-request state, exception type, and safe error message.
- A short SHA-256 fingerprint of the idempotency key for correlation; the raw key is never logged.

These fields answer the late-night questions: which phase failed, whether StoreLink was slow, what evidence the rule saw, whether a write reached StoreLink, and whether a retry was deduplicated.

### Category-buyer audit view

Buyer records are appended to `buyer.jsonl` and exposed through the MCP resource `audit://buyer/recent`. They avoid transport and latency terminology and instead show:

- What action was requested and which product and stores it affected.
- The rule applied in plain language.
- On-hand, last-24-hour POS, gap, decision, and reason for each store.
- Replenishment order IDs, quantities, status, and a plain-language summary.
- Whether the action was a safe retry that created no duplicate order.

The technical view is also available to authorized MCP clients at `audit://technical/recent`. Both recent resources return at most 100 in-process records; the JSONL files are the durable history for this exercise.

Set `STORELINK_AUDIT_DIR` to control where both files are written. It defaults to `/tmp/storelink-audit`. For a container deployment, mount that directory to durable storage:

```bash
docker run --rm --entrypoint storelink-buyer-demo -e STORELINK_AUDIT_DIR=/audit -v "$PWD/audit:/audit" storelink-buyer-mcp:exercise
```

Production follow-up would send the same JSON events to the organization's log platform with access controls and retention policies. Secrets, credentials, and raw idempotency keys must never be included.

Run the focused canary-based credential leak check with:

```bash
sh scripts/verify_no_secret_leaks.sh
```

The exact checked surfaces and limitations are documented in `docs/SECRET_VERIFICATION.md`.

## Structure

- `server.py`: six task-focused MCP tools and their descriptions
- `demo.py`: structured terminal walkthrough of the store replenishment request
- `audit.py`: correlated technical traces and buyer-readable audit records
- `service.py`: validation and deterministic business rules
- `storelink.py`: stubbed external API and idempotent write boundary
- `tests/`: service flow, validation, retry safety, and an in-memory MCP call
