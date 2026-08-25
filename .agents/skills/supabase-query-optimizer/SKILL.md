---
name: supabase-query-optimizer
description: Diagnose and optimize measured Supabase or PostgREST query problems such as slow queries, N+1 access, timeouts, excess requests, inefficient joins or counts, and missing indexes.
---

# Supabase Query Optimizer

Capture the slow workflow, request count, response sizes, query plans where available, and a representative dataset before changing code.

- Batch independent or repeated lookups and avoid N+1 query loops.
- Select only required columns; use server-side counts, filtering, pagination, and aggregation.
- Add indexes only when query predicates, ordering, data distribution, and plans justify them.
- Keep tenant predicates and authorization controls intact while optimizing.
- Include all result-changing parameters in cache keys and avoid duplicate fetches already satisfied by cache.
- Move authoritative business calculations into deterministic server-side functions rather than recomputing them in clients.

Re-run the same workflow and dataset. Report baseline and result for latency, request count, rows scanned or plan changes, and response size. Re-test correctness, empty results, tenant switching, and authorization; a faster query that weakens isolation or returns stale results is a regression.
