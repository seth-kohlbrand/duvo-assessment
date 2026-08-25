---
name: feature-design
description: Design substantial application features by mapping user journeys, entity lifecycles, prerequisites, operations, roles, failure modes, and testable acceptance criteria before implementation.
---

# Feature Design

Define the feature without assuming a business domain that the user has not stated.

- Identify actors, goals, entry points, prerequisites, and completion evidence.
- Model each entity's states, allowed transitions, ownership, and archival or deletion behavior.
- Separate deterministic business rules into server-side functions; do not ask an LLM or client to calculate authoritative outcomes.
- Define task-focused interfaces around user workflows instead of mirroring every storage or vendor API operation.
- Specify authorization and tenant scope at read, write, export, cache, and background-job boundaries.
- Define validation, idempotency, concurrency behavior, empty states, recovery paths, and observable errors.
- Write acceptance criteria covering the normal path, invalid input, unknown identifiers, duplicate requests, denied roles, cross-tenant attempts, and persistence after reload.

Prefer a small end-to-end slice that proves the architecture over a wide collection of disconnected screens or endpoints.
