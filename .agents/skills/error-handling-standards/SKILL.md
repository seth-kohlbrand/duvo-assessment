---
name: error-handling-standards
description: Add or review consistent failure handling across services, mutations, forms, uploads, API routes, background work, and error boundaries.
---

# Error Handling Standards

At every system boundary:

1. validate inputs and classify failures;
2. preserve the original cause in typed or structured errors;
3. log safe diagnostic context with an operation and correlation identifier;
4. return a stable machine-readable code and an actionable user-safe message;
5. report success only after the authoritative operation completes.

Reject malformed requests, unknown identifiers, negative quantities where invalid, and unauthorized targets. Never leak credentials, tokens, stack traces, database details, or another tenant's data.

Use conventional HTTP semantics where applicable: `400` validation, `401` unauthenticated, `403` unauthorized, `404` missing, `409` conflict, and `500` unexpected failure. Catch only when a layer can add context, translate, compensate, or present the error; otherwise propagate it. Keep corrective forms open, associate validation with fields, and prevent duplicate submission while pending.

Run `bash scripts/find-swallowed-errors.sh [path]` as a heuristic when useful and review matches manually. Test success plus validation, authorization, network, persistence, constraint, timeout, and duplicate-request failures. Confirm failed operations produce neither success UI nor partial state.
