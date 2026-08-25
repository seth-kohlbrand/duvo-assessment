# Supabase Review Checklist

Use this checklist after adapting the main skill to the current schema.

## Tenant boundary

- [ ] Tenant identity comes from authenticated context.
- [ ] User-scoped access is protected by tested RLS policies.
- [ ] Service-role operations include trusted tenant constraints.
- [ ] Query keys and storage paths partition tenant data.

## Query contract

- [ ] Selected fields and expected cardinality are explicit.
- [ ] Database errors propagate to the established error boundary.
- [ ] Joins, views, and RPCs preserve tenant scope.
- [ ] Pagination, count, and index needs follow observed access patterns.

## Mutation contract

- [ ] Editable input excludes tenant ownership and protected audit fields.
- [ ] Single-record mutations constrain by record ID and tenant ID.
- [ ] The response proves which row was affected.
- [ ] Cache updates happen only after commit.
- [ ] Reload or fresh-session verification confirms persistence.

## Schema and storage

- [ ] Migration works from the supported prior schema and on a clean database.
- [ ] Grants, RLS policies, constraints, indexes, and generated types are current.
- [ ] Storage policies enforce ownership independently of path naming.
- [ ] Sensitive objects remain private and signed URLs have suitable lifetimes.
