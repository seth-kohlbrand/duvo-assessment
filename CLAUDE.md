# Engineering standards for agents working in this repo

These standards are binding for any AI agent (Codex, Claude Code)
generating or modifying code here.

## Architecture
- All business logic and calculations live in deterministic,
  server-side functions. The agent/LLM never computes business
  rules, and no business rule is exposed as a tool parameter
  that a caller could alter.
- Expose a small set of task-focused tools designed around the
  user's workflow — never a 1:1 mirror of an underlying API.
- Layered modules: an API client layer (the only code that talks
  to external services), a business logic layer (pure functions,
  no network calls), and a tool/server layer that wires them
  together. No shortcuts across layers.

## Write-path safety
- The write path is strict: validate every input and reject
  anything malformed or inconsistent with the source data.
- Writes are idempotent.

## Secrets
- Secrets come from environment variables only. Never committed,
  never logged, never echoed in error messages.

## Verification
- Nothing is "done" until tests pass and the behavior has been
  exercised against real inputs.
- Documentation describes only commands that were actually run.
  No aspirational docs.

## Style
- Small, verifiable steps. Run tests before declaring anything
  complete.
- Prefer boring, readable code over clever code.