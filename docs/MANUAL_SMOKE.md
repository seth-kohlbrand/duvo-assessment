# Manual Smoke Suite

Run from the repository root.

## 1. Build

```bash
docker build -t storelink-buyer-mcp:exercise .
```

## 2. Run interactively

```bash
docker run --rm -i --entrypoint storelink-buyer-smoke storelink-buyer-mcp:exercise
```

The runner pauses at seven review points. At each prompt, check:

1. **MCP surface:** no API key, credential, password, or StoreLink key parameter is present.
2. **Buyer workflow:** store 47 has gap 9 and one order for 9 units; store 102 has gap 4 and no order.
3. **Audit views:** the buyer record is readable; the technical events include latency and rule evidence; both use the tool result's `operation_id`.
4. **Retry:** `duplicate_request` is `true` and no second order ID appears.
5. **Missing credentials:** store 999 fails before a StoreLink call, creates zero orders, and the buyer record says to contact Korral IT.
6. **Rotation recovery:** the trace shows `auth_rejected`, followed by `retried_after_rotation: true`; `raw_canary_visible` is `false`.
7. **Stale secret:** the error explains the source mismatch, StoreLink order count is zero, a failed buyer audit exists, and `raw_canary_visible` is `false`.

Expected final line:

```text
MANUAL SMOKE SUITE PASSED — all automated invariants held. Review the displayed evidence before sign-off.
```

The container uses `--rm`, so it is removed when the suite exits. If interrupted, check for a remaining exercise container with:

```bash
docker ps --filter ancestor=storelink-buyer-mcp:exercise
```

Stop only the listed exercise container if necessary:

```bash
docker stop <container-id>
```

## Non-interactive replay

To replay every scenario without prompts:

```bash
docker run --rm --entrypoint storelink-buyer-smoke storelink-buyer-mcp:exercise --no-pause
```

For the broader automated credential scan, also run:

```bash
sh scripts/verify_no_secret_leaks.sh
```
