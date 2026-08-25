---
name: supabase-patterns
description: Apply secure, reusable Supabase patterns for schema changes, tenant-scoped queries, mutations, storage, API boundaries, and row-level security.
---

# Supabase Patterns

Treat authenticated server context and RLS as security boundaries. Derive tenant identity from verified membership, not editable request fields. User-scoped clients should remain subject to RLS; service-role operations must add explicit tenant and record constraints because they bypass RLS.

Select only needed columns, check every returned error, and validate returned shapes at external boundaries. Put deterministic business logic and calculations in server-side database functions or application services. Keep public tools task-focused rather than exposing arbitrary table names, filters, or business-rule parameters.

Validate all writes, reject unknown related identifiers and invalid quantities, and make retried requests idempotent. Use constraints and transactions to preserve invariants under concurrency. Tenant-prefix storage paths and enforce ownership with storage policies.

For schema changes, use the migration, RLS, and SQL validation skills. For writes, verify the mutation round trip. Test allowed access, denied roles, cross-tenant record IDs, duplicate requests, and rollback or partial-failure behavior.
