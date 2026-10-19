# Poker platform infrastructure

Docker Compose and Helm compose independently owned application artifacts. Traefik owns HTTP/WebSocket routing. This repository has no runtime control service, application launcher or Docker socket inside a workload.

The available preview contains the Vue website and its real shared Flutter gameplay artifact. Authentication, accounts, money, poker and crypto endpoints remain foundation APIs; no login, payment or multiplayer flow is implied. Full startup fails until all private service images are verified and pinned in `artifacts.lock.json`.

- [Architecture and artifact ownership](docs/architecture.md)
- [Local development and verification](docs/development.md)
- [Compose and local Kubernetes](docs/deployment.md)
- [Version compatibility](docs/versioning.md)
- [Release checklist](docs/release_guide.md)

```sh
make install check
make preview-values
# After building the exact owner images identified by artifacts.lock.json:
make preview PROJECT=poker-platform-example
PLATFORM_TEST_URL=http://127.0.0.1:18080 make test-integration
make down PROJECT=poker-platform-example
```

Only an explicitly selected disposable local Kind cluster is authorized for Kubernetes execution. A remote cluster, production deploy, merge and release are outside this change.
