# Credential Leak Verification

Verified on August 26, 2026. This check is specifically about preventing StoreLink per-store credentials from reaching agent-visible or operational surfaces.

## Threat surfaces checked

- MCP tool names and input schemas: no API-key, credential, or password parameter exists.
- Successful tool results and safe authentication errors.
- FDE stderr traces and `technical.jsonl`.
- Buyer MCP audit resource and `buyer.jsonl`.
- Terminal demo output, including stderr.
- Repository files for common private-key and production-token patterns.
- Docker image configuration and full build history.

The tests inject distinctive canary credentials rather than real secrets. They exercise both a successful authenticated request and a stale-key authentication failure, then assert that the canary is absent from every returned, logged, persisted, and exception surface. Key fingerprints are expected because they permit correlation without revealing the key.

## Repeat the verification

From the repository root:

```bash
sh scripts/verify_no_secret_leaks.sh
```

Expected final line:

```text
PASS: tests, terminal output, repository scan, image config, and image history show no credential leakage
```

This is evidence for the implemented paths, not a claim that arbitrary future logging or an external log collector is safe. Run it after changes to authentication, exceptions, MCP schemas, Docker configuration, or observability.
