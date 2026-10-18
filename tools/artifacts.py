"""Validate immutable artifact identities and emit plain Compose/Helm values.

This module never runs Git, Docker, Helm, kubectl, shell commands or applications.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SERVICES = ("auth", "accounts", "virtual-money", "poker", "crypto")
EXPECTED_IMAGES = {"web", "gateway", "postgres", *SERVICES}
EXPECTED_CHARTS = {"service", "web", "gateway"}


def load_manifest(path: Path) -> dict[str, Any]:
    """Validate the supported schema and verify every vendored chart byte."""
    data: dict[str, Any] = json.loads(path.read_text())
    if (
        type(data["schemaVersion"]) is not int
        or data["schemaVersion"] != 1
        or (
            set(data["images"]) != EXPECTED_IMAGES
            or set(data["charts"]) != EXPECTED_CHARTS
        )
    ):
        raise ValueError("Unsupported artifact manifest schema or image inventory")
    game = data["game"]
    if (
        type(game["bridgeVersion"]) is not int
        or game["bridgeVersion"] != 1
        or re.fullmatch(r"[0-9a-f]{40}", game["clientCommit"]) is None
        or re.fullmatch(r"[0-9a-f]{64}", game["manifestSha256"]) is None
    ):
        raise ValueError("Incompatible or mutable Flutter artifact identity")
    for chart in [*data["charts"].values(), data["gatewayApi"]]:
        source = (path.parent / chart["file"]).resolve()
        if path.parent.resolve() not in source.parents:
            raise ValueError("Artifact path must remain in this repository")
        if hashlib.sha256(source.read_bytes()).hexdigest() != chart["sha256"]:
            raise ValueError("Vendored artifact checksum mismatch")
    return data


def image_ref(name: str, artifact: dict[str, Any], preview: bool) -> str:
    """Local tags are allowed only for the explicit non-deployment preview."""
    digest = artifact.get("digest", "")
    repository = artifact["repository"]
    if (
        not isinstance(repository, str)
        or re.fullmatch(
            r"ghcr\.io/[a-z0-9]+(?:[._-][a-z0-9]+)*/[a-z0-9]+(?:[._-][a-z0-9]+)*|postgres",
            repository,
        )
        is None
    ):
        raise ValueError("Use an approved image repository without interpolation")
    if not isinstance(digest, str):
        raise ValueError("Expected an immutable image digest")
    if digest and re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise ValueError("Expected an immutable image digest")
    if preview and name in {"web", "gateway"}:
        tag = artifact["localTag"]
        if (
            not isinstance(tag, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", tag) is None
            or tag == "latest"
        ):
            raise ValueError("Preview requires an explicit non-latest tag")
        return repository.rsplit("/", 1)[-1] + ":" + tag
    if digest:
        return repository + "@" + digest
    raise ValueError(
        f"Unpublished image {name}; private build/OCI acceptance is required"
    )


def emit(
    manifest_path: Path, output: Path, preview: bool, release: str, namespace: str
) -> None:
    """Write data only; all deployment commands remain in Make/Compose/Helm."""
    for name in (release, namespace):
        if re.fullmatch(r"[a-z](?:[a-z0-9-]{0,43}[a-z0-9])?", name) is None:
            raise ValueError("Use a bounded Kubernetes DNS release and namespace")
    data = load_manifest(manifest_path)
    selected = ("web", "gateway") if preview else tuple(data["images"])
    references = {
        name: image_ref(name, data["images"][name], preview) for name in selected
    }
    output.mkdir(parents=True, exist_ok=True)
    charts = output / "charts"
    charts.mkdir(exist_ok=True)
    for name, chart in data["charts"].items():
        (charts / (name + ".tgz")).write_bytes(
            (manifest_path.parent / chart["file"]).read_bytes()
        )
    lines = [
        f"{name.upper().replace('-', '_')}_IMAGE={value}"
        for name, value in references.items()
    ]
    (output / "compose.env").write_text("\n".join(lines) + "\n")
    for name in selected:
        if name == "gateway":
            continue
        if name == "postgres":
            (output / "postgres.values.json").write_text(
                json.dumps(
                    {
                        "image": references[name],
                        "localDevelopment": True,
                        "platformRelease": release,
                    },
                    indent=2,
                )
                + "\n"
            )
            continue
        artifact = data["images"][name]
        values: dict[str, Any] = {
            "image": {
                "repository": artifact["repository"],
                "digest": artifact.get("digest", ""),
            },
        }
        if preview:
            values.update(
                {
                    "localDevelopment": True,
                    "image": {
                        "repository": artifact["repository"].rsplit("/", 1)[-1],
                        "tag": artifact["localTag"],
                        "digest": "",
                    },
                }
            )
        if name in {"auth", "accounts"}:
            values.update(
                {
                    "database": {
                        "enabled": True,
                        "secretName": release + "-" + name + "-database",
                    },
                    "migration": {"enabled": True},
                }
            )
        (output / (name + ".values.json")).write_text(
            json.dumps(values, indent=2) + "\n"
        )
    gateway: dict[str, Any] = {
        "localDevelopment": True,
        "webService": release + "-web",
        "services": {
            source: release + "-" + target
            for source, target in {
                "authService": "auth",
                "accountsService": "accounts",
                "virtualMoney": "virtual-money",
                "pokerService": "poker",
                "cryptoService": "crypto",
            }.items()
        },
        "traefik": {
            "service": {"spec": {"type": "NodePort"}},
            "providers": {
                "kubernetesCRD": {"namespaces": [namespace]},
                "kubernetesGateway": {"namespaces": [namespace]},
            },
        },
    }
    (output / "gateway.values.json").write_text(json.dumps(gateway, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("artifacts.lock.json"))
    parser.add_argument("--output", type=Path, default=Path(".local/generated"))
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--release", default="platform")
    parser.add_argument("--namespace", default="foundation")
    args = parser.parse_args()
    emit(args.manifest, args.output, args.preview, args.release, args.namespace)


if __name__ == "__main__":
    main()
