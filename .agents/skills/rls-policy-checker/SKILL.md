---
name: rls-policy-checker
description: Review Supabase/PostgreSQL row-level-security changes for tenant isolation, recursion, privilege escalation, and missing operation coverage. Use when creating or modifying tenant-scoped tables, RLS policies, grants, or security-definer helpers.
---

# RLS Policy Review

Review the complete authorization path, not policy text in isolation.

## Table coverage

For each tenant-scoped table:

- enable RLS and decide whether `FORCE ROW LEVEL SECURITY` is appropriate for table owners;
- inventory grants by role;
- define the intended behavior for `SELECT`, `INSERT`, `UPDATE`, and `DELETE`;
- use `USING` for visibility of existing rows and `WITH CHECK` for proposed rows;
- verify that tenant identifiers cannot be reassigned through an update.

Missing a policy normally denies access, but broad grants, privileged clients, views, and functions can change the effective boundary. Inspect them together.

## Policy expressions

- Derive identity from trusted JWT claims or a controlled membership lookup.
- Qualify schema names in helpers and set a safe `search_path` on security-definer functions.
- Restrict function ownership and `EXECUTE` grants.
- Avoid volatile or unexpectedly expensive expressions in per-row policy checks.
- Review references to other RLS-protected tables for recursion and semantics. Such references are not categorically invalid; test the resulting policy graph.

## Migration safety

Create restrictive controls before exposing tenant data. Ensure policy and grant changes are transactional where practical, idempotent where repository conventions require it, and reversible through a reviewed follow-up migration.

## Tests

Exercise the deployed roles, not only an administrator:

1. tenant A can perform each authorized operation on its rows;
2. tenant A cannot select, insert for, update, or delete tenant B's rows;
3. attempted tenant reassignment fails;
4. unauthenticated access matches the product contract;
5. service-role behavior is separately tested and explicitly scoped in application code;
6. policy evaluation does not recurse or depend on mutable client input.

Report the table, role, operation, policy, positive result, and negative result. A policy is not approved based solely on successful creation or static SQL matching.
