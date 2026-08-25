---
name: tenant-query-audit
description: Review tenant-scoped query paths across database clients, service functions, hooks, APIs, cache keys, joins, RPCs, storage paths, and privileged access.
---

# Tenant Query Audit

For each query path, identify the tenant key, authenticated membership source, credential type, database policy, explicit predicate, cache or storage scope, and returned fields.

User-scoped clients rely on tested RLS as the security boundary; explicit tenant predicates remain useful defense in depth. Privileged clients bypass RLS, so derive scope from trusted server context and constrain reads and writes by both tenant and record identifier. Inspect actual join, view, RPC, and security-definer definitions. Security-definer functions need a safe search path, internal authorization, restricted execution grants, and negative tests.

Partition cache keys and local state by effective tenant, and prevent old in-flight responses from populating a new tenant context. Prefix storage objects by tenant and enforce the prefix in policy.

Pair static review with runtime negative tests: a principal from tenant A must not read, infer, update, delete, or attach tenant B's known record. Record evidence for each reviewed path and use `tenant-isolation-audit` for broader release-level coverage.
