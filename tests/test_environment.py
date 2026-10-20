"""Verify native settings priority and reject unsafe/incomplete plans before output."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tools.environment import DeploySettings, app, emit_environment

ROOT = Path(__file__).resolve().parents[1]


def test_priority_cli_environment_selected_file_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = tmp_path / "selected.env"
    selected.write_text("PLATFORM_HTTP_PORT=18101\nPLATFORM_ENVIRONMENT=dev\n")
    assert DeploySettings(_env_file=selected).http_port == 18101
    monkeypatch.setenv("PLATFORM_HTTP_PORT", "18102")
    assert DeploySettings(_env_file=selected).http_port == 18102
    assert DeploySettings(http_port=18103, _env_file=selected).http_port == 18103
    assert DeploySettings().environment == "local"  # no implicit dotenv
    state = tmp_path / "external-state"
    assert DeploySettings(state_dir=state).secret_dir == state / "secrets"
    result = CliRunner().invoke(
        app,
        [
            "--env-file",
            str(selected),
            "--environment",
            "ci",
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.stderr
    plan = json.loads((tmp_path / "out/plan.json").read_text())
    assert plan["settings"]["environment"] == "ci"
    assert plan["settings"]["http_port"] == 18102


def test_invalid_ports_paths_and_missing_pins_do_not_write(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError):
        DeploySettings(http_port=19090)
    with pytest.raises(ValidationError):
        DeploySettings(secret_dir=ROOT / ".local/secrets")
    with pytest.raises(ValidationError):
        DeploySettings(
            source_root=tmp_path / "external-sources",
            secret_dir=ROOT / ".local/secrets",
        )
    data = json.loads((ROOT / "artifacts.lock.json").read_text())
    del data["images"]["auth"]["sourceCommit"]
    # Keep real vendored bytes; isolate only the missing-pin input.
    from unittest.mock import patch

    with patch("tools.environment.load_manifest", return_value=data):
        with pytest.raises(ValueError, match="sourceCommit"):
            emit_environment(
                DeploySettings(), ROOT / "artifacts.lock.json", tmp_path / "out"
            )
    assert not (tmp_path / "out").exists()


def test_remote_is_prepared_only_and_contains_no_secret_values(tmp_path: Path) -> None:
    output = tmp_path / "prepared"
    emit_environment(
        DeploySettings(environment="remote"), ROOT / "artifacts.lock.json", output
    )
    plan = json.loads((output / "plan.json").read_text())
    assert plan["execution"] == "prepared-only"
    env = (output / "compose.env").read_text()
    assert "DATABASE_URL" not in env and "password=" not in env.lower()
    assert all(
        "@sha256:" in plan["images"][name]
        for name in ("prometheus", "grafana", "loki", "alloy")
    )


def test_environment_snapshots_survive_preparation_and_rollback(tmp_path: Path) -> None:
    """Preparing another environment cannot mutate an active bind-mounted file."""
    output = tmp_path / "generated"
    manifest = ROOT / "artifacts.lock.json"
    emit_environment(DeploySettings(environment="local"), manifest, output)
    first = json.loads((output / "plan.json").read_text())
    directory = Path(first["config_dir"])
    before = {path.name: path.read_bytes() for path in directory.iterdir()}
    emit_environment(DeploySettings(environment="dev"), manifest, output)
    second = json.loads((output / "plan.json").read_text())
    assert first["config_dir"] != second["config_dir"]
    assert before == {path.name: path.read_bytes() for path in directory.iterdir()}
    emit_environment(DeploySettings(environment="local"), manifest, output)
    assert json.loads((output / "plan.json").read_text())["config_dir"] == str(
        directory
    )
    (directory / "alloy.alloy").write_text("corrupted-derived-config")
    with pytest.raises(ValueError, match="snapshot is damaged"):
        emit_environment(DeploySettings(environment="local"), manifest, output)
