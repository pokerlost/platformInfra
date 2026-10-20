"""Validate immutable artifact identities and emit plain Compose/Helm values.

This module never runs Git, Docker, Helm, kubectl, shell commands or applications.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from tools.artifact_models import EXPECTED_IMAGES as EXPECTED_IMAGES
from tools.artifact_models import (
    ArtifactManifest,
    ImageArtifact,
    ResourceNames,
)


def load_manifest(path: Path) -> dict[str, Any]:
    """Validate the supported schema and verify every vendored chart byte."""
    try:
        manifest = ArtifactManifest.model_validate_json(path.read_text())
    except ValidationError as error:
        category = (
            "Flutter identity"
            if any(
                item["loc"] and item["loc"][0] == "game"
                for item in error.errors(include_input=False, include_context=False)
            )
            else "schema or image inventory"
        )
        raise ValueError("Unsupported artifact " + category) from None
    data: dict[str, Any] = manifest.model_dump(by_alias=True, exclude_unset=True)
    for chart in [*data["charts"].values(), data["gatewayApi"]]:
        source = (path.parent / chart["file"]).resolve()
        if path.parent.resolve() not in source.parents:
            raise ValueError("Artifact path must remain in this repository")
        if hashlib.sha256(source.read_bytes()).hexdigest() != chart["sha256"]:
            raise ValueError("Vendored artifact checksum mismatch")
    return data


def image_ref(name: str, artifact: dict[str, Any], preview: bool) -> str:
    """Local tags are allowed only for the explicit non-deployment preview."""
    try:
        validated = ImageArtifact.model_validate(artifact)
    except ValidationError:
        raise ValueError("Invalid immutable image, tag or repository") from None
    digest = validated.digest
    repository = validated.repository
    if preview and name in {"web", "gateway"}:
        tag = validated.local_tag
        if tag is None or tag == "latest":
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
    try:
        ResourceNames(release=release, namespace=namespace)
    except ValidationError:
        raise ValueError("Use a bounded Kubernetes DNS release and namespace") from None
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
    if not preview:
        lines.extend(
            f"{name.upper()}_IMAGE={value}"
            for name, value in data.get("observability", {}).items()
        )
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
    gateway_artifact = data["images"]["gateway"]
    gateway_image = {
        "repository": gateway_artifact["repository"],
        "tag": "",
        "digest": gateway_artifact.get("digest") or None,
    }
    if preview:
        gateway_image = {
            "repository": gateway_artifact["repository"].rsplit("/", 1)[-1],
            "tag": gateway_artifact["localTag"],
            "digest": None,
        }
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
            "image": gateway_image,
            "versionOverride": "v3.7.15",
            "service": {"spec": {"type": "NodePort"}},
            "providers": {
                "kubernetesCRD": {"namespaces": [namespace]},
                "kubernetesGateway": {"namespaces": [namespace]},
            },
        },
    }
    (output / "gateway.values.json").write_text(json.dumps(gateway, indent=2) + "\n")


app = typer.Typer(
    help=__doc__,
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_show_locals=False,
)


@app.command()
def main(
    manifest: Annotated[Path, typer.Option("--manifest")] = Path("artifacts.lock.json"),
    output: Annotated[Path, typer.Option("--output")] = Path(".local/generated"),
    preview: Annotated[bool, typer.Option("--preview")] = False,
    release: Annotated[str, typer.Option("--release")] = "platform",
    namespace: Annotated[str, typer.Option("--namespace")] = "foundation",
) -> None:
    """Emit data only; no deployment or external commands are executed."""
    try:
        emit(manifest, output, preview, release, namespace)
    except (ValueError, OSError) as error:
        message = (
            str(error) if isinstance(error, ValueError) else "Artifact file unavailable"
        )
        typer.echo(message, err=True)
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
