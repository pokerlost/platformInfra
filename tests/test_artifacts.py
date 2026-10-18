"""Exercise actual file/integrity boundaries of the data-only artifact adapter."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.artifacts import EXPECTED_IMAGES, emit, image_ref, load_manifest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    data: dict[str, Any] = {
        "schemaVersion": 1,
        "game": {
            "clientCommit": "a" * 40,
            "manifestSha256": "b" * 64,
            "bridgeVersion": 1,
        },
        "images": {
            name: {
                "repository": "ghcr.io/pokerlost/" + name,
                "digest": "sha256:" + "c" * 64,
                "localTag": "candidate",
            }
            for name in EXPECTED_IMAGES
        },
        "charts": {},
        "gatewayApi": {
            "file": "gateway-api.yaml",
            "sha256": hashlib.sha256(b"synthetic-crd-input").hexdigest(),
        },
    }
    for name in ("service", "web", "gateway"):
        file = tmp_path / (name + ".tgz")
        file.write_bytes(b"synthetic-checksum-input")
        data["charts"][name] = {
            "file": file.name,
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
    (tmp_path / "gateway-api.yaml").write_bytes(b"synthetic-crd-input")
    path = tmp_path / "artifacts.lock.json"
    path.write_text(json.dumps(data))
    return path


def change(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data))


def test_full_values_preserve_artifact_identity_and_database_capabilities(
    manifest: Path, tmp_path: Path
) -> None:
    output = tmp_path / "generated"
    emit(manifest, output, False, "demo", "isolated")
    env = (output / "compose.env").read_text()
    assert len(env.splitlines()) == 8 and "@sha256:" in env
    for name in ("auth", "accounts"):
        value = json.loads((output / (name + ".values.json")).read_text())
        assert value["database"]["secretName"] == "demo-" + name + "-database"
        assert value["migration"] == {"enabled": True}
    for name in ("web", "virtual-money", "poker", "crypto"):
        value = json.loads((output / (name + ".values.json")).read_text())
        assert "database" not in value and "migration" not in value
        assert value["image"]["digest"] == "sha256:" + "c" * 64
    postgres = json.loads((output / "postgres.values.json").read_text())
    assert postgres["localDevelopment"] and postgres["platformRelease"] == "demo"
    gateway = json.loads((output / "gateway.values.json").read_text())
    assert (
        gateway["webService"] == "demo-web"
        and gateway["services"]["accountsService"] == "demo-accounts"
    )
    assert gateway["traefik"]["providers"]["kubernetesGateway"]["namespaces"] == [
        "isolated"
    ]
    assert (output / "charts/service.tgz").read_bytes() == b"synthetic-checksum-input"
    assert "DATABASE_URL" not in env


def test_preview_allows_only_explicit_web_gateway_tags(
    manifest: Path, tmp_path: Path
) -> None:
    data = load_manifest(manifest)
    for image in data["images"].values():
        image["digest"] = ""
    change(manifest, data)
    output = tmp_path / "preview"
    emit(manifest, output, True, "p", "foundation")
    assert (output / "compose.env").read_text().splitlines() == [
        "WEB_IMAGE=web:candidate",
        "GATEWAY_IMAGE=gateway:candidate",
    ]
    assert json.loads((output / "web.values.json").read_text())["localDevelopment"]
    assert not (output / "auth.values.json").exists()
    with pytest.raises(ValueError, match="Unpublished"):
        image_ref("auth", data["images"]["auth"], True)
    with pytest.raises(ValueError, match="Unpublished"):
        emit(manifest, tmp_path / "full", False, "demo", "foundation")


@pytest.mark.parametrize(
    "field,value",
    [("schemaVersion", 2), ("schemaVersion", True), ("images", {}), ("charts", {})],
)
def test_invalid_inventory(manifest: Path, field: str, value: object) -> None:
    data = json.loads(manifest.read_text())
    data[field] = value
    change(manifest, data)
    with pytest.raises(ValueError, match=r"schema|inventory"):
        load_manifest(manifest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bridgeVersion", 2),
        ("bridgeVersion", True),
        ("clientCommit", "main"),
        ("manifestSha256", "latest"),
    ],
)
def test_incompatible_game_identity(manifest: Path, field: str, value: object) -> None:
    data = json.loads(manifest.read_text())
    data["game"][field] = value
    change(manifest, data)
    with pytest.raises(ValueError, match="Flutter"):
        load_manifest(manifest)


def test_changed_or_escaping_vendored_chart(manifest: Path, tmp_path: Path) -> None:
    data = json.loads(manifest.read_text())
    (tmp_path / "service.tgz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_manifest(manifest)
    data["charts"]["service"]["file"] = "../escape.tgz"
    change(manifest, data)
    with pytest.raises(ValueError, match="remain"):
        load_manifest(manifest)


@pytest.mark.parametrize(
    "artifact",
    [
        {"repository": "ghcr.io/pokerlost/web", "digest": "latest"},
        {"repository": 12, "digest": "sha256:" + "a" * 64},
        {"repository": "ghcr.io/pokerlost/web", "digest": 1},
        {"repository": "ghcr.io/pokerlost/web", "localTag": 1},
        {"repository": "ghcr.io/pokerlost/web", "localTag": "latest"},
        {"repository": "ghcr.io/pokerlost/web", "localTag": "bad tag"},
        {
            "repository": "other-registry.example/private",
            "digest": "sha256:" + "a" * 64,
        },
        {
            "repository": "ghcr.io/pokerlost/web\nINJECTED=yes",
            "digest": "sha256:" + "a" * 64,
        },
    ],
)
def test_rejects_mutable_or_interpolated_images(artifact: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"immutable|tag|repository"):
        image_ref("web", artifact, True)


@pytest.mark.parametrize(
    "release,namespace",
    [("bad;command", "foundation"), ("demo", "trailing-"), ("x" * 46, "foundation")],
)
def test_rejects_invalid_resource_names(
    manifest: Path, tmp_path: Path, release: str, namespace: str
) -> None:
    with pytest.raises(ValueError, match="DNS"):
        emit(manifest, tmp_path / "output", True, release, namespace)


def test_real_cli_emits_data_only_and_does_not_touch_manifest(
    manifest: Path, tmp_path: Path
) -> None:
    before = manifest.read_bytes()
    output = tmp_path / "cli"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.artifacts",
            "--manifest",
            str(manifest),
            "--output",
            str(output),
            "--preview",
        ],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert manifest.read_bytes() == before and (output / "web.values.json").is_file()
    assert not (output / "kubeconfig").exists()


def test_changed_crd_is_rejected_before_deployment(
    manifest: Path, tmp_path: Path
) -> None:
    (tmp_path / "gateway-api.yaml").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        load_manifest(manifest)
