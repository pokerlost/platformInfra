# Metrics and correlated logs

[Home](../README.md) · [Architecture](architecture.md) · [Operations](operations.md)

The full Compose profile includes official pinned Prometheus, Grafana, Loki and
Alloy images. Image versions/digests live only in `artifacts.lock.json`.
FastAPI owns reusable native prometheus-client/instrumentator instrumentation and
standard structured logging; serviceTemplate owns identity. PlatformInfra owns
collector configuration, storage and provisioned dashboards/datasources.
There is no custom exporter, shipper, runtime monitoring service or SaaS default.

## Actual signals and cardinality

API counters and histogram durations use seconds, route templates, bounded status
and fixed service/environment values. Unknown/untemplated paths are grouped;
raw HTTP methods are not an API metric label. In-flight is the official Gauge.
Per-app registries avoid duplicate registration when tests create multiple apps;
Compose uses one worker per container. Scale containers instead of silently using
an unconfigured multiworker registry. Prometheus scrapes process CPU seconds and
resident bytes from the five APIs and Traefik. This is process-level coverage;
no host/full-container or Nginx-process resource collection is claimed.

Alloy's embedded official blackbox exporter probes five internal liveness and
readiness endpoints (ten fixed targets), then remote-writes to local Prometheus.
Prometheus also scrapes Alloy's own health metrics. Probes/metrics/admin endpoints
are absent from public gateway routing. No Docker socket, host process/journal,
whole HOME, privileged exporter or cluster-wide access is mounted.

Native Docker stdout syslog is UDP, nonblocking with a 1 MiB buffer and bounded
2 MiB x 2 local dual-log cache per app. Fixed tags identify seven producers.
Alloy sends JSON to Loki with only fixed environment/service labels (and the
collector's constant service_name); request_id and level are structured metadata.
Raw URL/query, user/session/table IDs, tokens, exception messages and private cards
are excluded from metric/index labels and safe application logs. The SDK can
explicitly propagate a correlation ID; routing identity is not authorization.

The gateway validates/replaces an external `X-Request-ID`; internal hops preserve
it and return one response header. Traefik access-log original input is redacted
in Alloy; the authoritative downstream response ID is used for correlation.
Nginx/API logs record the same ID. Grafana's log panel and derived fields query
actual Loki entries without a stream per request. Exceptions log their class,
not arbitrary traceback/message contents or request query/body/bearer values.

## Storage, limits and access

Prometheus flags set 15 days and 2048 MB retention plus compressed WAL; the size
flag is a TSDB retention target, not a filesystem quota (WAL/temporary overhead
requires headroom). Loki uses TSDB v13, 24h index periods, filesystem object
storage, 168h retention, enabled compactor retention and a 2h deletion delay.
Defaults are configurable through validated settings. Native ingestion/rate,
cache and memory limits bound resource use. This daemon's extfs local volumes
provide no verified hard filesystem quota for Loki: an owner-approved quota-backed
volume is still required for a hard disk-size guarantee. Short tests verify config
readback and persistence, not seven or fifteen days of elapsed retention.

Memory/CPU ceilings: Prometheus 512 MiB/1 CPU, Loki 512 MiB/1 CPU, Alloy 256 MiB/0.5
CPU, Grafana 256 MiB/0.5 CPU. Named volumes retain metrics, logs and Grafana SQLite
state. Provisioning files are Git-owned immutable config snapshots, separate from
those volumes. Grafana's local secret bootstrap copies only its exact credential
into its own private volume; no host ownership changes occur.

Admin listeners bind loopback only. Grafana has a generated private password,
no anonymous users/signup, update reporting or automatic plugin preinstallation.
The small management bridge enables those loopback publications; it is not an
Internet exposure/auth model. Remote use needs separately approved auth/TLS.

## Acceptance

```bash
make accept-local
```

The test emits correlated requests, requires both backend counters and histogram
counts to increase, finds logs from both APIs, gateway and static web, verifies
request_id is absent from Loki index labels, checks six process metric sources,
all ten probes and collector health, queries both Grafana datasources and every
provisioned Prometheus panel plus the real Loki panel query. The private local
receipt is `coverage/observability.json`. Failed/missing data fails acceptance;
YAML, Ready status and a dashboard JSON alone are insufficient.
