---
name: migration-safety
description: Review Supabase/PostgreSQL migrations for repeatability, locking, compatibility, rollback risk, and production-safe sequencing. Use for schema changes or migration failures, including duplicate-object and missing-object errors.
---

# Migration Safety

Treat applied migrations as immutable history. Follow the repository's migration tool and ordering conventions; repair an already-deployed change with a new migration unless the project explicitly permits otherwise.

## Choose repeatability deliberately

Migration runners normally apply each version once. Idempotent guards are useful for bootstrap scripts and some repair migrations, but `IF NOT EXISTS` can hide an object whose definition differs from the intended schema. Use a guard only when an existing object is acceptable and verify its shape when correctness depends on it.

Do not suppress `duplicate_object` broadly around policy or constraint creation. Prefer an explicit catalog check followed by a definition comparison, or drop and recreate the object when that transition is safe and intended.

## Review before execution

Establish:

- supported source schema and target schema;
- PostgreSQL and Supabase feature versions;
- estimated table size and lock behavior;
- compatibility with the currently deployed application;
- backfill cost, batching, and restart behavior;
- rollback or forward-recovery strategy;
- RLS, grants, triggers, views, generated types, and dependent functions affected.

## Safer sequencing

For changes that cannot be deployed atomically with the application, prefer expand-and-contract:

1. add a backward-compatible nullable column or new object;
2. deploy code that can read old and new forms;
3. backfill in bounded, restartable batches;
4. validate data and constraints;
5. switch reads and writes to the new form;
6. remove the obsolete form in a later migration.

Use `NOT VALID` followed by `VALIDATE CONSTRAINT` where appropriate to separate creation from validation. Create large indexes concurrently only when supported by the migration runner and outside a transaction block.

## Data and constraint checks

- Query for nulls, duplicates, or invalid values before tightening constraints.
- Use stable keys and deterministic predicates for restartable backfills.
- Make conflict handling preserve the intended data; do not use `DO NOTHING` merely to silence errors.
- Verify expression indexes and `NULLS NOT DISTINCT` against the deployed PostgreSQL version.
- Keep tenant and RLS changes restrictive throughout the deployment sequence.

## Verification

Test both a clean database and an upgrade from the oldest supported prior schema. Run the repository's migration status/diff tooling, focused SQL assertions, generated-type update, and application tests that exercise affected reads and writes.

Before any remote push, resolve the exact project and environment with a read-only check. Production execution requires explicit user authorization. Use `sql-batch-validator` for preflight diagnostics and `rls-policy-checker` for authorization changes.

Report the migration, source state tested, target state observed, timing or lock concerns, verification results, and recovery plan.
