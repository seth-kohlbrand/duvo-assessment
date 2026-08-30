# Agent connection demo — Claude Code over MCP

The demo is implemented as a script, not just this document:

```bash
scripts/agent_demo.sh [idempotency-key]
```

It builds the server image, generates an MCP config pointing at this
checkout, connects a real agent (Claude Code in headless mode) to the
containerized stdio server, and drives the pilot buyer task through it.
Everything below is from an actual run on August 30, 2026; the raw
artifacts it produced are in `demo_artifacts/`:

- `mcp-config.json` — the generated agent-side config
- `tool_list.txt` — the tool surface as the agent reported it
- `agent_run.jsonl` — the full stream-json transcript of the buyer task
- `tool_calls.txt` — the tool calls extracted from that transcript
- `final_answer.md` — the agent's final answer verbatim

Requires `docker`, the `claude` CLI, and `jq`.

## How the agent connects

The script writes this config (absolute audit-volume path filled in for
the current checkout) and passes it to `claude -p` with
`--mcp-config … --strict-mcp-config --allowedTools "mcp__storelink__*"`:

```json
{
  "mcpServers": {
    "storelink": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "-e", "STORELINK_AUDIT_DIR=/audit",
        "-v", "<repo>/audit:/audit",
        "storelink-buyer-mcp:exercise"
      ]
    }
  }
}
```

No StoreLink secret is passed because the stub provides its own
self-consistent credentials — a production config would add the
`KORRAL_STORE_KEY_*` variables or mount `KORRAL_STORE_KEYS_DIR` here.
A copy of the same block lives at `mcp-config.json` in the repo root for
interactive use; edit its absolute path to match your checkout.

## Step 1 — smoke check: the agent sees the tool surface

The script first asks the agent to list the storelink tools. Observed
output (`demo_artifacts/tool_list.txt`) — exactly the six intended tools:

```
mcp__storelink__get_purchase_order
mcp__storelink__list_categories
mcp__storelink__plan_replenishment
mcp__storelink__replenish_store_stock
mcp__storelink__review_category
mcp__storelink__submit_replenishment
```

## Step 2 — the pilot buyer task, driven by the agent

The script then gives the agent the buyer task: SKU 8847291 may be
running low at stores 47 and 102; investigate, replenish what needs it
under a fresh idempotency key, then prove the write is retry-safe by
re-issuing the identical call.

StoreLink tool calls the agent made (`demo_artifacts/tool_calls.txt`,
run of 2026-08-30, key `agent-demo-20260830-192142`; the file's first
line is the harness's own `ToolSearch` schema load, not a server call):

```
mcp__storelink__replenish_store_stock {"sku":"8847291","store_ids":[47,102],"idempotency_key":"agent-demo-20260830-192142"}
mcp__storelink__replenish_store_stock {"sku":"8847291","store_ids":[47,102],"idempotency_key":"agent-demo-20260830-192142"}
```

The first call returned the server's full evidence: store 47 had 3
on-hand against 12 units of 24-hour POS (gap 9 > 6 → replenish, order
`R47-0001` for 9 units); store 102 had 8 on-hand (gap 4 → no action).
The second, identical call came back flagged `duplicate_request: true`
with the same order `R47-0001` — no second write.

### Agent's final answer (verbatim excerpt, `demo_artifacts/final_answer.md`)

> - **Store 47 — replenished.** On hand 3 units vs. 12 sold in the last
>   24 hours, a gap of 9 units, above the 6-unit threshold. The server
>   created replenishment order **R47-0001** for 9 units, submitted
>   2026-08-30, status `received`.
> - **Store 102 — no action.** On hand 8 units vs. 12 sold, a gap of
>   only 4 units, under the threshold, so no order was placed.
>
> **Retry-safety proof:** I re-issued the exact same call with the same
> idempotency key … The server recognized it as a duplicate
> (`duplicate_request: true`) and returned the **same order R47-0001**
> rather than creating a second order.

## What this run demonstrated

- A real agent (not a bespoke driver script) connected to the server
  over stdio MCP, discovered the six tools, and completed the pilot
  buyer task end to end.
- The business rule ran server-side. The agent never supplied a
  threshold, quantity, or formula; the tool schemas do not accept them.
- Write-path safety held: the retry with a reused idempotency key
  produced `duplicate_request` and zero additional writes.
- Both audit views were written through the mounted volume
  (`audit/buyer.jsonl`, `audit/technical.jsonl`). The script prints the
  last buyer records; the run above produced:

  ```
  Replenishment was placed for store(s) 47; all other checked stores required no action.
  This was a safe retry; no duplicate replenishment orders were created.
  ```
