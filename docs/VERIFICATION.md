# Verification

Verified on August 26, 2026 from the repository root.

## Container build

Command executed:

```bash
docker build -t storelink-buyer-mcp:exercise .
```

Result: succeeded using Python 3.12 and FastMCP 2.14.7.

## Server startup

Command executed:

```bash
docker run --rm -i storelink-buyer-mcp:exercise
```

Result: FastMCP started `StoreLink Category Buyer` with the stdio transport and exited normally when stdin closed. There is intentionally no HTTP port.

## Automated tests

Command executed:

```bash
docker run --rm --entrypoint sh -v "$PWD:/workspace:ro" -w /workspace storelink-buyer-mcp:exercise -c "pip install -q 'pytest>=8,<9' 'pytest-asyncio>=0.24,<2' && PYTHONPATH=src python -m pytest -q"
```

Result: `21 passed`.

The tests exercised:

- MCP discovery of all six tools and a real in-memory MCP tool call.
- The full buyer flow: category review, replenishment planning, submission, retry, and purchase-order lookup.
- Deterministic reorder quantity and cost calculations against the StoreLink stub data.
- Rejection of unknown category, product, plan, and purchase-order identifiers.
- Rejection of an empty idempotency key.
- Safe retry behavior: the second submission returned the original purchase order and created no duplicate side effect.
- Store-level validation, fixed gap calculation, conditional replenishment, and idempotent retry behavior.
- Fresh per-request secret loading, successful mid-flight key-rotation recovery, bounded failure when the secret source remains stale, and rejection of an uncredentialed store before StoreLink is called.
- Failure audit records with zero orders and no raw credential or idempotency-key values.

## Buyer-request terminal demo

Command executed:

```bash
docker run --rm --entrypoint storelink-buyer-demo storelink-buyer-mcp:exercise
```

Result: the demo printed six structured steps through a real in-memory MCP client. For SKU `8847291`, store 47 had a 9-unit gap and received replenishment order `R47-0001` for 9 units. Store 102 had a 4-unit gap and received no order because the fixed rule requires a gap greater than 6. Repeating the call with the same idempotency key returned `duplicate_request: true` without another order.

The demo now also prints two correlated observability views: a buyer-readable action record and the FDE trace containing workflow phases, dependency latency, rule evidence, write outcome, and total duration. Tests verify that both views share the returned `operation_id`, both JSONL files are written, and the raw idempotency key appears in neither log.

The FastMCP dependency emitted an upstream Authlib deprecation warning; it did not affect startup or test results.

## Credential leak verification

Command executed:

```bash
sh scripts/verify_no_secret_leaks.sh
```

Result: tests, canary-based terminal checks, repository pattern scan, Docker image configuration, and full image history all passed with no credential leakage. See `docs/SECRET_VERIFICATION.md` for the checked surfaces and limitations.

## Manual smoke suite replay

Command executed:

```bash
docker run --rm --entrypoint storelink-buyer-smoke storelink-buyer-mcp:exercise --no-pause
```

Result: all seven smoke scenarios completed and the runner printed `MANUAL SMOKE SUITE PASSED`. The run exercised the actual in-memory MCP client, both MCP audit resources, retry deduplication, missing-store failure, successful rotation recovery, stale-secret zero-write failure, and raw-canary absence checks.
