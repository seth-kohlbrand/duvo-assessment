---
name: workflow-testing
description: Trace and test multi-step application workflows end to end from user action through UI state, API boundaries, server logic, persistence, cache refresh, and later reads.
---

# End-to-End Workflow Testing

Start from the user's trigger and trace every handoff: control or route, handler, validation, mutation, API, deterministic server-side business logic, data store, response, cache update, and rendered result. Identify stubs, disconnected callbacks, hidden disabled states, missing migrations, swallowed errors, and optimistic success without persistence.

Exercise the workflow with real test inputs through the same boundary users invoke. For state changes, verify the authoritative stored result, reload the page, start a fresh session, and confirm the state through the normal read path. Test the same action from each entry point that exposes it.

Cover valid input, malformed input, unknown identifiers, invalid negative quantities, duplicate submission, retry after interruption, denied roles, cross-tenant identifiers, conflicts, and dependency failures. Confirm errors are actionable and safe, dialogs retain correctable input, failures create no partial state, and successful writes refresh every dependent view.

Use `mutation-round-trip` for persistence proof and `error-handling-standards` when failures are silent, misleading, or unsafe. Report exact inputs, observed outputs, stored results, reload results, negative tests, and commands actually run.
