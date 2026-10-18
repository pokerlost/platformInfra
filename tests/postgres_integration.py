"""Execute real TCP queries using the generated Secret in an explicit local Kind."""

from __future__ import annotations

import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest


@pytest.mark.parametrize("database", ["auth", "accounts"])
def test_current_secret_authenticates_over_tcp(database: str) -> None:
    cluster = os.environ["PLATFORM_TEST_KIND_NAME"]
    config = Path(os.environ["PLATFORM_TEST_KUBECONFIG"]).resolve()
    assert cluster.startswith("poker-platform-") and config.is_file()
    command = [
        os.environ.get("KUBECTL", "kubectl"),
        "--kubeconfig",
        str(config),
        "--context",
        "kind-" + cluster,
        "--namespace",
        "foundation",
    ]
    server = subprocess.check_output(
        [
            *command,
            "config",
            "view",
            "--minify",
            "-o",
            "jsonpath={.clusters[0].cluster.server}",
        ],
        text=True,
        timeout=15,
    )
    assert server.startswith(("https://127.0.0.1:", "https://localhost:"))
    name = "postgres-check-" + uuid.uuid4().hex[:12]
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": name,
            "labels": {"app.kubernetes.io/managed-by": "platform-infra-tests"},
        },
        "spec": {
            "activeDeadlineSeconds": 60,
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 60,
            "template": {
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 999,
                        "runAsGroup": 999,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "client",
                            "image": "foundation-postgres:local-2d2b8998d310",
                            "imagePullPolicy": "Never",
                            "command": [
                                "psql",
                                "-X",
                                "--no-password",
                                "-Atc",
                                "SELECT current_database()",
                            ],
                            "env": [
                                {
                                    "name": "PGHOST",
                                    "value": "platform-" + database + "-db",
                                },
                                {"name": "PGUSER", "value": "app"},
                                {"name": "PGDATABASE", "value": database},
                                {
                                    "name": "PGPASSWORD",
                                    "valueFrom": {
                                        "secretKeyRef": {
                                            "name": "platform-"
                                            + database
                                            + "-database",
                                            "key": "POSTGRES_PASSWORD",
                                        }
                                    },
                                },
                            ],
                            "resources": {
                                "requests": {"cpu": "10m", "memory": "16Mi"},
                                "limits": {"cpu": "100m", "memory": "64Mi"},
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                },
            },
        },
    }
    subprocess.run(
        [*command, "create", "-f", "-"],
        input=json.dumps(job),
        text=True,
        check=True,
        capture_output=True,
        timeout=20,
    )
    try:
        completed = subprocess.run(
            [
                *command,
                "wait",
                "--for=condition=complete",
                "job/" + name,
                "--timeout=70s",
            ],
            text=True,
            capture_output=True,
            timeout=80,
        )
        logs = subprocess.check_output(
            [*command, "logs", "job/" + name], text=True, timeout=15
        )
        assert completed.returncode == 0, logs
        assert logs.strip() == database
    finally:
        subprocess.run(
            [*command, "delete", "job/" + name, "--wait=true", "--timeout=30s"],
            check=True,
            capture_output=True,
            timeout=40,
        )
