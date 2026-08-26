# Shipping to Korral

## Where it runs

Run the Duvo agent and this MCP server together inside **Korral's private GCP tenancy**, preferably in the same private GKE pod (or on a Korral-managed private VM). The workload uses private routing to StoreLink, has no public ingress, and has default-deny egress except for approved Korral services. Logs, traces, audits, images, and backups remain in Korral's GCP projects; customer data is not sent to Duvo or third-party telemetry.

The server uses stdio, so the agent launches it as a local child process rather than calling a public MCP endpoint. The supplied image runs with the StoreLink stub; production promotion is blocked until the stub transport is replaced and tested against Korral's private StoreLink endpoint.

## Build, delivery, and ownership

Duvo owns source, tests, the Dockerfile, dependency updates, and release notes. CI builds an immutable image, runs tests and smoke suites, scans it, generates an SBOM, and signs it. The image is copied to Artifact Registry in Korral's project.

Korral owns the deployment pipeline, production service account, network policy, Secret Manager access, final approval, and rollback. Duvo can prepare releases and hotfixes but cannot deploy production without Korral's pipeline and audit trail.

```bash
docker build -t storelink-buyer-mcp:exercise .
docker run --rm --entrypoint storelink-buyer-smoke storelink-buyer-mcp:exercise --no-pause
```

Production references the tested image digest, never a mutable tag. Promote the same digest from private staging to a production canary and retain the previous known-good digest for immediate rollback.

## Secrets

Korral IT stores one key per store in GCP Secret Manager. Prefer a Secret Manager CSI-mounted volume at `KORRAL_STORE_KEYS_DIR` with files such as `store_47.key`. `KORRAL_STORE_KEY_47` environment variables are supported but less desirable because process configuration can expose them.

The image contains no keys. Workload Identity grants access only to required store secrets. Keys are read on every request, so weekly rotation needs no restart. A rejected key causes one fresh read and one retry; a still-stale key fails with zero writes and creates technical and buyer audit records. Raw keys are never returned or logged.

## An 11pm fix

1. Correlate buyer audit and private Cloud Logging with `operation_id`; classify code, StoreLink, network, or key-rotation failure.
2. If a recent release caused it, Korral rolls back to the previous signed digest immediately.
3. Otherwise Duvo prepares a small reviewed hotfix. CI reruns tests, smoke and leak checks, image scanning/signing, and private-staging verification.
4. Korral approves and canary-deploys the new digest, watches errors, latency, and writes, then rolls forward or back.

Production data and logs stay inside Korral. Emergency access is time-bound, least-privileged, and recorded in Korral's audit system.

## Confirm before day 1

- GCP project/region, GKE or VM runtime, private DNS/routes/firewalls to StoreLink, and allowed egress.
- Artifact Registry, signing/SBOM/vulnerability policy, approvers, rollout windows, rollback SLO, and on-call ownership.
- StoreLink URL, TLS/mTLS, timeouts/rate limits, idempotency semantics, and private staging data.
- Store-to-secret inventory, CSI layout, rotation timing/grace period, and the 24/7 owner for stale or missing keys.
- Workload Identity permissions, audit retention/access, alert routes, incident process, and data-retention rules.
- Confirmation that dependencies, pulls, logs, metrics, traces, and backups remain in approved Korral GCP boundaries.
