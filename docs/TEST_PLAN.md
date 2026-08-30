# Test plan and results

A requirement-driven pytest suite derived from the five steps of the
project brief. Each test ID below exists as a named test so the suite
doubles as a compliance checklist. The step-organized files complement
`tests/test_service.py` and `tests/test_mcp.py`, which grew alongside
the implementation.

## Layout

```
tests/
  conftest.py                  shared fixtures (stub transport, env-key client, audit dir)
  test_step1_tool_surface.py   agent-facing contract
  test_step2_buyer_task.py     the pilot buyer task + write-path safety
  test_step3_observability.py  FDE trace + buyer audit
  test_step4_secrets.py        key loading, rotation, missing credentials
  test_step5_container.py      Docker artifact smoke (marker: container)
  test_service.py, test_mcp.py implementation-era tests, kept
```

## What each step verifies

**Step 1 — surface** (`test_step1_tool_surface.py`)
- S1-1 exactly the six intended tools, each described.
- S1-2 no business-rule input (threshold, quantity, cost, cover days) on any tool schema.
- S1-3 `review_category` returns evidence an agent can reason over.
- S1-4 reorder math is server-side: coffee → 34 units, tea → 0, total 425.0.
- S1-5 both audit views are published as MCP resources.
- S1-6 unknown identifiers fail safely, naming the identifier.

**Step 2 — the buyer task** (`test_step2_buyer_task.py`)
- S2-1 SKU 8847291 at stores 47+102: store 47 (on-hand 3, POS 12, gap 9) gets a
  9-unit order; store 102 (gap 4) gets nothing; exactly one order exists.
- S2-2 every store check carries on-hand, POS, gap, threshold, decision, reason.
- S2-3 the created order is retrievable with status `received`.
- S2-4 category plan → submit → purchase-order status flow works.
- W-1 ten malformed-request variants are rejected with zero writes.
- W-2 idempotent retry returns the same order, creating no second write.
- W-3 idempotency-key reuse with a different payload is rejected (409).
- W-4 a failure on any requested store means no partial writes at all.

**Step 3 — observability** (`test_step3_observability.py`)
- S3-1 one `operation_id` ties workflow start, upstream requests, rule
  evaluations, the write, and completion together, in causal order.
- S3-2 latencies and dependency names are recorded on reads, writes, requests.
- S3-3 the buyer record is plain language: product name, the 6-unit rule, which
  stores were replenished.
- S3-4 failures produce both a technical `workflow.failed` and a buyer-visible
  record with a next step, sharing the operation ID.
- S3-5 `technical.jsonl` / `buyer.jsonl` are durable and line-parseable.
- S3-6 audit is readable over MCP and correlates to the tool result's operation ID.
- S3-7 nothing is printed to stdout (reserved for the stdio transport).

**Step 4 — secrets** (`test_step4_secrets.py`, using the production
`StoreKeyProvider` path, not the stub's self-consistent provider)
- S4-1 env keys are read fresh per request; a rotation needs no restart.
- S4-2 mounted key files work; env wins; whitespace files count as missing.
- S4-3 rotation mid-flight: one 401, one re-read, one retry, one write.
- S4-4 rotation with a stale secret source: exactly one attempt, an error naming
  the store and stating nothing was changed, pointing at Korral IT; zero writes.
- S4-5 missing store credential: fails before any StoreLink call, listing the
  stores that are configured.
- S4-6 traces carry 8-hex key fingerprints; raw key material appears nowhere.
- S4-7 both failure messages reach the MCP client verbatim, not masked.

**Step 5 — artifact** (`test_step5_container.py`, `-m container`, needs Docker)
- S5-1 the image builds.
- S5-2 the entire suite passes inside the image's own Python environment.
- S5-3 the containerized stdio server answers a real MCP client's `list_tools`.
- S5-4 the demo entrypoint replenishes store 47 and not store 102.

## Commands run and results (August 26, 2026)

```bash
docker build -q -t storelink-buyer-mcp:testplan .

docker run --rm --entrypoint sh -v "$PWD:/workspace:ro" -w /workspace \
  storelink-buyer-mcp:testplan -c \
  "pip install -q 'pytest>=8,<9' 'pytest-asyncio>=0.24,<2' && \
   PYTHONPATH=src python -m pytest -q -m 'not container' -p no:cacheprovider"
# → 62 passed, 4 deselected

python3 -m pytest tests/test_step5_container.py -q -m container
# → 4 passed  (host side; drives docker itself)
```

The only warning is an upstream Authlib deprecation notice from FastMCP;
it does not affect behavior.
