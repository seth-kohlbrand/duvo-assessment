---
name: mutation-round-trip
description: Verify that application mutations persist through the authoritative data store and remain correct after reload, fresh sessions, tenant changes, role checks, retries, and duplicate requests.
---

# Mutation Round-Trip

Trace each write from user action through validation, authorization, server logic, persistence, response handling, cache updates, and subsequent reads.

Use a stable target identifier and record the before state. Perform the mutation through the real application boundary, verify the authoritative stored result, then reload and start a fresh session to prove the read path returns the same state. Switch tenants and roles to confirm the record is neither exposed nor mutable outside its scope.

Test malformed input, unknown identifiers, invalid negative quantities, conflicts, interrupted requests, retries, and duplicate submission. Repeating the same idempotency key or request must not create duplicate side effects. Verify affected counts, related records, events, and cache entries—not only the primary row.

Completion evidence must name the input used, authoritative read performed, reload or fresh-session result, negative authorization checks, duplicate-request result, and commands actually run.
