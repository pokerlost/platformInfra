# Development

Git, Make and Docker run the primary reproducible adapter checks. `make check` runs locked
Ruff, strict mypy and all 31 data-only adapter tests once; `make coverage` reads that fresh
result. Whole-source statements and branches remain separate under `coverage/python/`.
Below 100% warns; real test/type/configuration/build and missing/corrupt/stale report failures
remain errors. Runtime integration is explicit and is never replaced by a skipped success.

```bash
make check
make coverage
make config-check
```

`config-check` generates preview values in a dedicated output mount, validates native Compose
and the owner Helm charts, and does not pull missing backend artifacts. `.local` as a whole,
secrets and the user HOME/socket are never mounted into the quality container. `make build`
and `make image` are explicitly notApplicable: composition consumes existing verified images.

`make preview`, `down`, `status` and `logs` use Compose directly. `down` preserves volumes.
For an already running preview, set `PLATFORM_TEST_URL` and run `make verify` or
`make test-integration`; Docker tests check real routes, CSP/cache behavior and Flutter
manifest/bootstrap hashes. Browser lifecycle and responsive rendering belong to pokerWeb;
Traefik TLS/WS/failure/drain scenarios belong to pokerGateway.

Host/CI control steps use checksum-pinned Kind, Helm and kubectl for an explicit disposable
local cluster and kubeconfig. `make test-database` runs the real TCP/Secret PostgreSQL tests
inside Docker, mounting only that exact kubeconfig read-only and requiring a localhost Kind
server. `make cluster`, `kube-secrets`, `deploy-preview`, `deploy-local` and `undeploy-local`
use the existing native tools; they do not introduce a runtime orchestrator. Full startup
requires every immutable backend artifact and the separately owner-activated B1 acceptance.
A preview is not full platform readiness. Remote cluster use remains forbidden in this task.
