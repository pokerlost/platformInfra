"""Query the real local profile; this suite never starts or administers workloads."""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
from pydantic import SecretStr

from tools.environment import DeploySettings

ROOT = Path(__file__).resolve().parents[1]


def eventually(description: str, condition: Callable[[], bool]) -> None:
    """Wait for native scrape/batch latency; permanent access errors still raise."""
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(1)
    raise AssertionError(description)


def test_real_metrics_logs_and_provisioned_dashboard() -> None:
    plan = json.loads(Path(os.environ["PLATFORM_TEST_PLAN"]).read_text())
    settings = DeploySettings(**plan["settings"])
    if settings.environment == "remote":
        raise AssertionError("Only an explicitly selected local profile is testable")
    edge = f"http://127.0.0.1:{settings.http_port}"
    prometheus = f"http://127.0.0.1:{settings.prometheus_port}"
    loki = f"http://127.0.0.1:{settings.loki_port}"
    grafana = f"http://127.0.0.1:{settings.grafana_port}"
    request_id = "accept-" + uuid4().hex
    environment = settings.environment
    selector = f'environment="{environment}",handler="/getOpenApi"'
    with httpx.Client(trust_env=False, timeout=15) as client:

        def query(expression: str) -> list[dict[str, Any]]:
            response = client.get(
                prometheus + "/api/v1/query", params={"query": expression}
            )
            response.raise_for_status()
            body = response.json()
            assert body["status"] == "success"
            return cast(list[dict[str, Any]], body["data"]["result"])

        def counts(metric: str) -> dict[str, float]:
            expression = f"sum by (service_id) ({metric}{{{selector}}})"
            return {
                row["metric"]["service_id"]: float(row["value"][1])
                for row in query(expression)
            }

        # A restarted process may still have an older sample under identical
        # labels. Establish a fresh native scrape before measuring a delta.
        started = time.time()

        def fresh_backend_scrapes() -> bool:
            targets = (
                f'up{{environment="{environment}",'
                'service_id=~"authService|accountsService"}'
            )
            rows = query(f"(timestamp({targets}) > {started}) and ({targets} == 1)")
            return {"authService", "accountsService"} <= {
                row["metric"].get("service_id") for row in rows
            }

        eventually("No fresh successful backend scrapes", fresh_backend_scrapes)
        counter_before = counts("http_requests_total")
        histogram_before = counts("http_request_duration_seconds_count")
        for service in ("authService", "accountsService"):
            for _ in range(12):
                response = client.get(
                    edge + "/getOpenApi",
                    headers={
                        "x-pokerlost-serviceId": service,
                        "X-Request-ID": request_id,
                    },
                )
                assert response.status_code == 200
                assert response.headers["X-Request-ID"] == request_id
        static = client.get(edge + "/", headers={"X-Request-ID": request_id})
        assert static.status_code == 200
        assert static.headers["X-Request-ID"] == request_id

        def has_increased(metric: str, before: dict[str, float]) -> bool:
            current = counts(metric)
            return all(
                current.get(service, 0) >= before.get(service, 0) + 12
                for service in ("authService", "accountsService")
            )

        for metric, before in (
            ("http_requests_total", counter_before),
            ("http_request_duration_seconds_count", histogram_before),
        ):
            eventually(
                f"{metric} did not record both real backend requests",
                partial(has_increased, metric, before),
            )
        eventually(
            "Not all ten liveness/readiness probes are healthy",
            lambda: (
                len(query(f'probe_success{{environment="{environment}"}} == 1')) == 10
            ),
        )
        eventually(
            "Collector scrape is not healthy",
            lambda: bool(
                query(f'up{{job="collector",environment="{environment}"}} == 1')
            ),
        )
        for metric in ("process_cpu_seconds_total", "process_resident_memory_bytes"):
            rows = query(f'{metric}{{environment="{environment}"}}')
            assert {
                "authService",
                "accountsService",
                "virtualMoney",
                "pokerService",
                "cryptoService",
                "pokerGateway",
            } <= {row["metric"].get("service_id") for row in rows}
        log_query = f'{{environment="{environment}"}} | request_id="{request_id}"'

        def logs() -> list[dict[str, Any]]:
            response = client.get(
                loki + "/loki/api/v1/query_range",
                params={"query": log_query, "limit": 1000},
            )
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json()["data"]["result"])

        eventually(
            "Correlated logs did not arrive from API and static hops",
            lambda: (
                {"pokerGateway", "authService", "accountsService", "pokerWeb"}
                <= {row["stream"]["service_id"] for row in logs()}
            ),
        )
        for stream in logs():
            if stream["stream"]["service_id"] == "pokerGateway":
                continue
            for record in stream["values"]:
                assert json.loads(record[1])["environment"] == environment
        labels = client.get(loki + "/loki/api/v1/labels")
        labels.raise_for_status()
        assert "request_id" not in labels.json()["data"]
        series = client.get(
            loki + "/loki/api/v1/series",
            params={"match[]": f'{{environment="{environment}"}}'},
        )
        series.raise_for_status()
        assert all("request_id" not in row for row in series.json()["data"])
        password = SecretStr(
            (settings.secret_dir / "grafana-admin-password").read_text()
        )
        auth = httpx.BasicAuth("operator", password.get_secret_value())
        for uid in ("prometheus", "loki"):
            health = client.get(
                grafana + f"/api/datasources/uid/{uid}/health", auth=auth
            )
            health.raise_for_status()
            assert health.json()["status"] == "OK"
        response = client.get(
            grafana + "/api/dashboards/uid/pokerlost-local", auth=auth
        )
        response.raise_for_status()
        dashboard = response.json()["dashboard"]
        panels = []

        def panel_has_data(expression: str) -> bool:
            result = client.get(
                grafana + "/api/datasources/proxy/uid/prometheus/api/v1/query",
                params={"query": expression},
                auth=auth,
            )
            result.raise_for_status()
            values = result.json()["data"]["result"]
            return any(math.isfinite(float(row["value"][1])) for row in values)

        for panel in dashboard["panels"]:
            if panel["datasource"]["uid"] != "prometheus":
                continue
            expression = panel["targets"][0]["expr"]
            expression = expression.replace("$environment", environment)
            expression = expression.replace("${service:regex}", ".*")
            # A newly selected environment needs two native scrapes for rate().
            # Keep the same finite-data assertion and bounded scrape wait.
            eventually(
                f"Panel has no actual finite data: {panel['title']}",
                partial(panel_has_data, expression),
            )
            panels.append(panel["title"])
        result = client.get(
            grafana + "/api/datasources/proxy/uid/loki/loki/api/v1/query_range",
            params={"query": log_query, "limit": 1000},
            auth=auth,
        )
        result.raise_for_status()
        assert result.json()["data"]["result"]
        output = ROOT / "coverage/observability.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "environment": environment,
                    "configSha256": plan["config_sha256"],
                    "requestId": request_id,
                    "counterBefore": counter_before,
                    "counterAfter": counts("http_requests_total"),
                    "histogramBefore": histogram_before,
                    "histogramAfter": counts("http_request_duration_seconds_count"),
                    "logServices": sorted(
                        {row["stream"]["service_id"] for row in logs()}
                    ),
                    "requestIdNotIndexed": True,
                    "healthyProbeCount": 10,
                    "grafanaDatasourceHealth": ["prometheus", "loki"],
                    "panelsWithActualData": panels,
                },
                indent=2,
            )
            + "\n"
        )
