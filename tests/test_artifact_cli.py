"""Exercise the native Typer boundary without touching live configuration."""

import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from rich.text import Text
from typer.testing import CliRunner

from tools.artifact_models import ArtifactManifest
from tools.artifacts import app


@pytest.mark.parametrize("color", [False, True])
def test_help_has_no_side_effects(
    tmp_path: Path, monkeypatch: MonkeyPatch, color: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        ["--help"],
        color=color,
        env={
            "CI": "true",
            "GITHUB_ACTIONS": "true",
            "FORCE_COLOR": "1" if color else None,
            "NO_COLOR": None if color else "1",
        },
    )
    assert result.exit_code == 0
    assert "--manifest" in Text.from_ansi(result.stdout).plain
    assert not result.stderr
    assert not list(tmp_path.iterdir())


def test_bad_and_extra_arguments() -> None:
    for arguments in (["--manifest"], ["unexpected"], ["--unknown"]):
        result = CliRunner().invoke(app, arguments)
        assert result.exit_code == 2
        assert result.stderr


def test_invalid_manifest_redacts_input(tmp_path: Path) -> None:
    path = tmp_path / "параметры проверки.json"
    sentinel = "private-token-value-do-not-print"
    path.write_text(json.dumps({"schemaVersion": sentinel}))
    output = tmp_path / "output"
    result = CliRunner().invoke(
        app, ["--manifest", str(path), "--output", str(output), "--preview"]
    )
    assert result.exit_code == 1
    assert not result.stdout
    assert sentinel not in result.stderr
    assert "Unsupported artifact" in result.stderr
    assert not output.exists()


def test_manifest_schema_keeps_wire_aliases() -> None:
    schema = ArtifactManifest.model_json_schema()
    assert "schemaVersion" in schema["properties"]
    assert "gatewayApi" in schema["properties"]
    assert "schema_version" not in schema["properties"]
