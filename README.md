# Poker platform infrastructure

Compose owns the full local profile: Vue + the real versioned Flutter bundle,
Nginx, Traefik, five foundation APIs, two PostgreSQL databases and
Prometheus/Grafana/Loki/Alloy. This is the platform deployment entrypoint.
Authentication/accounts and the money/poker/crypto services are foundations;
multiplayer gameplay, ledger and payments are not implemented by this composition.

- [Architecture and ownership](docs/architecture.md)
- [Clean checkout and configuration](docs/deployment.md)
- [Metrics, correlated logs and retention](docs/observability.md)
- [Restart, upgrade, rollback and recovery](docs/operations.md)
- [Development checks](docs/development.md)
- [Artifact compatibility](docs/versioning.md) and [delivery boundaries](docs/release_guide.md)

After preparing the pinned clean sources, the verified client bundle and the
private SDK source cache as described in the deployment guide:

```bash
make config validate plan PLATFORM_ENV_FILE="$local_env"
make build-or-reuse PLATFORM_ENV_FILE="$local_env"
make up PROJECT=poker-platform-example PLATFORM_ENV_FILE="$local_env"
make status PROJECT=poker-platform-example
make down PROJECT=poker-platform-example
```

`up` runs real HTTP, Prometheus, Loki and Grafana acceptance before recording an
active manifest. It reuses built images and preserves named storage. The `local`
mode works without seven published service images; `registry` mode fails before
startup while any required digest or private pull connection is missing. Remote
settings are prepared configuration only. See the guides before selecting paths.

## License

Original source and documentation use [MIT](LICENSE). Preserve the
[third-party notices](THIRD_PARTY_NOTICES.md) and bundled upstream license texts.
Dependency licenses and private-data access do not change with this license.

Run `make help` for native tasks, `make version` for canonical artifact versions,
and `make ci-local` for the local required checks and `coverage/ci-local.json`.
`make release-check` validates built artifact identity; it does not publish or tag.
See [version and release policy](docs/versioning.md).
