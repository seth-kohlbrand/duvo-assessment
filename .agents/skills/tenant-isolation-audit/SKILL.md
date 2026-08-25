---
name: tenant-isolation-audit
description: Verify tenant isolation across database policies, application queries, APIs, caches, storage, background jobs, seed data, exports, and visible application surfaces.
---

# Tenant Isolation Audit

Establish the documented tenant key and how authenticated identities map to it. Trace that authority across every boundary; a client-side filter or text search is not proof of isolation.

Audit:

- RLS coverage for select, insert, update, and delete;
- user-scoped and privileged server queries;
- joins, views, RPCs, aggregates, exports, and search;
- cache keys, in-flight requests, local state, and tenant switching;
- storage object paths and signed URLs;
- jobs, integrations, seed data, logs, and notifications.

Use two tenants with known distinct records. For each relevant role, verify allowed access and attempt to read, mutate, delete, enumerate, export, or infer the other tenant's known identifiers. Confirm failed attempts create no side effects and disclose no sensitive existence or metadata. Verify child records cannot reference parents from another tenant and that privileged paths constrain both tenant and record identifiers.

Report the tested path, credential type, tenant source, enforcing control, negative test, and result. Treat missing operation coverage or a successful cross-tenant attempt as a release blocker.
