# Engineering Standards for AI Agents

## Architecture

- All business logic and calculations live in deterministic server-side functions.
- The agent or LLM never computes business rules.
- No business rule may be exposed as a tool parameter.
- Tools are designed around the user's workflow as roughly 5–6 task-focused tools, never as a 1:1 mirror of an underlying API.

## Write-path safety

- Validate all inputs.
- Reject negative quantities, unknown identifiers, and malformed requests.
- Writes must be idempotent so duplicate requests never create duplicate side effects.

## Secrets

- Use environment variables only.
- Never commit or log secrets.
- Read rotatable keys at request time rather than caching them at startup.

## Verification

- Nothing is done until tests pass and behavior has been exercised against real inputs.
- Documentation may describe only commands that were actually run.

## Style

- Work in small, verifiable steps.
- Run tests before declaring anything complete.
- Prefer boring, readable code over clever code.
