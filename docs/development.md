# Development

Use Python 3.14 and uv 0.12.15. `make install` synchronizes the lock; `make check` runs Ruff, strict mypy and all data-adapter tests with whole-source statement/branch coverage at 100%. Unimported production modules remain in the denominator. Reports are written under `coverage/`. Integration tests are a separate explicit target and are never replaced with a skipped success.

```sh
make install check preview-values
docker compose --project-name infra-check --file compose.yaml --env-file .local/generated/compose.env config --quiet
helm lint .local/generated/charts/web.tgz --strict --values .local/generated/web.values.json
helm lint .local/generated/charts/gateway.tgz --strict --values .local/generated/gateway.values.json
```

For an already running preview, set `PLATFORM_TEST_URL` and run `make test-integration`. Tests verify actual route status, private API fallbacks, CSP, cache headers and the downloaded Flutter manifest/bootstrap SHA. Browser lifecycle, accessibility and responsive rendering tests belong to pokerWeb and run against the same production image. Traefik HTTP/TLS/WebSocket and shutdown tests belong to pokerGateway.

CI validates the adapter, actual Compose parsing and owner charts without pretending unpublished service images are available. Local runtime acceptance is recorded separately. Dependency cache keys are scoped to the private source repository; this repository has no production image and does not export an image build cache.

`.local`, `.aws`, environment files, credentials, coverage data, agent metadata, memory dumps and backups are outside source/artifact inputs. Never copy actual credential directories into an archive or test fixture. Privacy regressions use synthetic markers only.
