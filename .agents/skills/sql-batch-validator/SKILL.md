---
name: sql-batch-validator
description: Statically inspect and optionally execute PostgreSQL or Supabase SQL files with statement-level diagnostics. Use for migration, seed, RLS, or schema SQL when batch validation or controlled database execution is requested.
---

# SQL Batch Validator

Use the bundled scripts from this skill directory and resolve their paths relative to `SKILL.md`.

## Static validation

Static checks do not require database access:

```bash
python3 scripts/validate_sql.py path/to/file.sql
python3 scripts/validate_sql.py path/to/file.sql --verbose
printf 'SELECT 1;' | python3 scripts/validate_sql.py --stdin
```

The validator is a focused preflight tool, not a PostgreSQL parser. Treat its findings as leads and use a real database or established migration tooling for authoritative syntax and schema validation. Read [common pitfalls](references/common-pitfalls.md) when a reported pattern needs explanation.

## Database execution

Executing SQL changes external state. Do it only when the user has authorized the target database and the connection has been verified as non-production or production access was explicitly requested.

The executor requires a direct PostgreSQL connection:

```bash
python3 scripts/run_sql_batch.py path/to/file.sql \
  --database-url "$DATABASE_URL" \
  --transaction \
  --verbose
```

Useful modes:

- `--dry-run` parses and statically validates without connecting.
- `--transaction` commits only when every statement succeeds.
- `--stop-on-error` stops non-transactional execution after the first failure.
- `--output-json report.json` writes a machine-readable result.

Avoid putting credentials in command history or output. Prefer an existing, scoped environment variable and never include secrets in the handoff.

## Workflow

1. Inspect the SQL and its migration order.
2. Run static validation and review warnings in context.
3. Use the repository's normal local database or migration test when available.
4. Before remote execution, identify the exact project and environment with a read-only check.
5. Prefer a transaction for migrations that can run transactionally.
6. Report applied, rolled-back, skipped, and failed statements accurately.

For RLS changes, also use `rls-policy-checker`; static SQL validation cannot prove authorization behavior.
