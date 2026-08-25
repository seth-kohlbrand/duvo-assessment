---
name: edge-function-patterns
description: Implement and review Supabase Edge Functions with explicit authentication, tenant scoping, secret handling, bounded external calls, idempotent writes, and structured errors.
---

# Supabase Edge Function Patterns

Follow versions and shared utilities already pinned in the repository.

At request boundaries, allow only expected methods, validate origins and input, verify authentication, derive user and tenant identity from trusted server-side context, and authorize the exact target operation. Never trust a client-supplied tenant identifier as authority.

Use user-scoped clients when RLS should apply. Service-role clients bypass RLS, so constrain every operation by authenticated tenant scope and record identity. Read secrets from environment configuration at request time and never return or log them.

Bound external calls with timeouts and retry only retry-safe operations. Validate response status and shape. Make writes idempotent so repeated requests do not duplicate side effects.

Return stable status codes, safe messages, error codes, and correlation identifiers. Preserve useful diagnostic causes in protected logs. Test missing and invalid credentials, forbidden records, malformed input, absent configuration, timeouts, partial failure, duplicate requests, and cross-tenant attempts.
