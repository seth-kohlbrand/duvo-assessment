---
name: component-performance
description: Diagnose React rendering and client data-cache performance when measured slowdowns, excessive renders, stale data, cache collisions, or subscription leaks are suspected.
---

# Component Performance

Measure the failing workflow before optimizing. Use profiling, browser traces, network inspection, query devtools, or focused counters to identify the dominant cost and establish a baseline.

- Include every result-changing input, including tenant scope, in cache keys.
- Prevent an old request from updating state after its scope or parameters change.
- Keep frequently changing state close to its consumers.
- Use memoization only when measurement or required referential stability justifies it.
- Paginate or virtualize large collections based on observed DOM and query cost.
- Invalidate or update only affected cache entries after successful writes.
- Scope subscriptions narrowly and clean them up on dependency changes and unmount.

Compare the same workflow and dataset before and after. Re-test scope switching, empty states, mutation refresh, and subscription cleanup; improved speed cannot come at the cost of stale or cross-tenant results.
