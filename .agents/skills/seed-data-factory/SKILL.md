---
name: seed-data-factory
description: Create realistic, tenant-safe, repeatable development, test, or demonstration data with environment guards, deterministic identifiers, idempotency, and cleanup.
---

# Seed Data Factory

Confirm the target is a non-production environment before writing. Require an explicit environment guard and fail closed when the environment is unknown.

Create a small coherent dataset using deterministic identifiers or stable natural keys. Scope every tenant-owned row explicitly, keep relationships within the same tenant, and include at least two tenants when isolation behavior needs testing. Validate inputs and referenced identifiers before mutation. Use upserts or existence checks so reruns converge without duplicate side effects.

Do not include real personal data, credentials, production identifiers, or domain assumptions the user has not supplied. Provide a cleanup path scoped only to the seed namespace and verify both a second run and cleanup against real development or test inputs.
