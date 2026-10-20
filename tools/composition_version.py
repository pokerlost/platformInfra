"""Version and validate the independently versioned declarative composition."""

from __future__ import annotations

import hashlib
import json
import re
import tarfile
import tomllib
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(no_args_is_help=True)


def versions() -> dict[str, Any]:
    version = Path("VERSION").read_text().strip()
    if not re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?", version
    ):
        raise ValueError("Invalid composition SemVer")
    manifest = json.loads(Path("artifacts.lock.json").read_text())
    return {
        "composition": version,
        "verificationTools": tomllib.loads(Path("pyproject.toml").read_text())[
            "project"
        ]["version"],
        "manifestSchema": manifest["schemaVersion"],
        "manifestSha256": hashlib.sha256(
            Path("artifacts.lock.json").read_bytes()
        ).hexdigest(),
        "components": {
            "images": manifest["images"],
            "charts": manifest["charts"],
            "game": manifest["game"],
            "observability": manifest["observability"],
        },
    }


@app.command("release-check")
def release_check() -> None:
    expected = versions()
    source = json.loads(Path("coverage/source.json").read_text())
    if source["dirty"]:
        raise ValueError("Composition archive requires a clean reviewed commit")
    archive = Path("dist") / f"platform-infra-{expected['composition']}.tar.gz"
    prefix = f"platform-infra-{expected['composition']}/"
    with tarfile.open(archive) as data:
        version_file = data.extractfile(prefix + "VERSION")
        manifest_file = data.extractfile(prefix + "artifacts.lock.json")
        if (
            version_file is None
            or version_file.read().decode().strip() != expected["composition"]
        ):
            raise ValueError("Composition archive version mismatch")
        if (
            manifest_file is None
            or hashlib.sha256(manifest_file.read()).hexdigest()
            != expected["manifestSha256"]
        ):
            raise ValueError("Composition archive manifest mismatch")
    if Path("coverage/composition-source.txt").read_text().strip() != source["commit"]:
        raise ValueError("Composition source receipt mismatch")
    records = [
        {
            "path": str(archive),
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "version": expected["composition"],
        }
    ]
    Path("coverage/artifacts.json").write_text(json.dumps(records, indent=2) + "\n")
    Path("coverage/versions.json").write_text(json.dumps(expected, indent=2) + "\n")
    print("Composition version, archived manifest and source identity agree.")


@app.command("version")
def show_version() -> None:
    """Show native composition, verification and component identities."""
    typer.echo(json.dumps(versions(), indent=2))


if __name__ == "__main__":
    app()
