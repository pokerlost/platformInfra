"""Version and validate the independently versioned declarative composition."""

from __future__ import annotations

import hashlib
import json
import tarfile
import tomllib
from pathlib import Path

import typer
from pydantic import BaseModel, ConfigDict, Field

from docker.release import Source
from tools.artifacts import load_manifest

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


class CompositionVersion(BaseModel):
    """Only this composition owns its version; component schema stays canonical."""

    model_config = ConfigDict(strict=True)
    composition: str = Field(
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"
    )
    verification_tools: str = Field(serialization_alias="verificationTools")
    manifest_schema: int = Field(serialization_alias="manifestSchema")
    manifest_sha256: str = Field(
        serialization_alias="manifestSha256", pattern=r"^[0-9a-f]{64}$"
    )
    components: dict[str, object]


def versions() -> CompositionVersion:
    manifest = load_manifest(Path("artifacts.lock.json"))
    return CompositionVersion(
        composition=Path("VERSION").read_text().strip(),
        verification_tools=tomllib.loads(Path("pyproject.toml").read_text())["project"][
            "version"
        ],
        manifest_schema=manifest["schemaVersion"],
        manifest_sha256=hashlib.sha256(
            Path("artifacts.lock.json").read_bytes()
        ).hexdigest(),
        components={
            name: manifest[name]
            for name in ("images", "charts", "game", "observability")
        },
    )


@app.command("release-check")
def release_check() -> None:
    expected = versions()
    source = Source.model_validate_json(Path("coverage/source.json").read_text())
    if source.dirty or source.commit is None:
        raise ValueError("Composition archive requires a clean reviewed commit")
    archive = Path("dist") / f"platform-infra-{expected.composition}.tar.gz"
    prefix = f"platform-infra-{expected.composition}/"
    with tarfile.open(archive) as data:
        version_file = data.extractfile(prefix + "VERSION")
        manifest_file = data.extractfile(prefix + "artifacts.lock.json")
        if (
            version_file is None
            or version_file.read().decode().strip() != expected.composition
        ):
            raise ValueError("Composition archive version mismatch")
        if (
            manifest_file is None
            or hashlib.sha256(manifest_file.read()).hexdigest()
            != expected.manifest_sha256
        ):
            raise ValueError("Composition archive manifest mismatch")
    if Path("coverage/composition-source.txt").read_text().strip() != source.commit:
        raise ValueError("Composition source receipt mismatch")
    records = [
        {
            "path": str(archive),
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "version": expected.composition,
        }
    ]
    Path("coverage/artifacts.json").write_text(json.dumps(records, indent=2) + "\n")
    Path("coverage/versions.json").write_text(
        expected.model_dump_json(by_alias=True, indent=2) + "\n"
    )
    print("Composition version, archived manifest and source identity agree.")


@app.command("version")
def show_version() -> None:
    """Show native composition, verification and component identities."""
    typer.echo(versions().model_dump_json(by_alias=True, indent=2))


if __name__ == "__main__":
    app()
