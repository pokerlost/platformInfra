# Development

[Home](../README.md) · [Deployment](deployment.md)

```bash
make check
make coverage
make config-check
```

The locked native quality recipe runs Ruff, strict mypy and data-adapter tests.
The current owner suite has 42 tests; whole-source coverage is advisory below
100%, while actual failures and missing/corrupt/stale reports fail. CI separates
configuration/unit/chart checks from real PostgreSQL/Secret/Kind verification.
`make build`/`make image` are notApplicable for this data-only repo;
`build-or-reuse` invokes native builds in the seven artifact owners.

The adapters validate inputs and emit data only. Integration tests query an
explicit running local plan and do not administer Docker or Kubernetes. `up`
runs `tests/platform_integration.py` and `tests/observability_integration.py` on
host uv because admin listeners are loopback. Browser lifecycle/responsiveness is
verified by pokerWeb's production Playwright image on the task-owned ingress
network with `POKER_WEB_BASE_URL=http://gateway:8080`. Run it after native startup
and separately from resource-heavy builds. Traefik HTTP/2, TLS, WS, failure and
drain acceptance belongs to pokerGateway and uses real technical upstreams.

Native config checks run before runtime/secret side effects. The quality image
receives only selected output/kubeconfig mounts; application workloads never
receive Docker sockets or the source HOME. Chart/Kind tool versions and checksums
are job-local. An explicit disposable local kubeconfig/context is mandatory.
No current remote context, production deployment or broader SDK App admission is
part of these tests. Keep baseline backups, refs and previous rollback artifacts.
