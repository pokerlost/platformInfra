"""Validate deployment inputs and emit data; never execute infrastructure commands."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import typer
import yaml
from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tools.artifacts import image_ref, load_manifest

Port = Annotated[int, Field(ge=1024, le=65535)]


class DeploySettings(BaseSettings):
    """Explicit init inputs override environment, selected dotenv and defaults."""

    model_config = SettingsConfigDict(
        env_prefix="PLATFORM_", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["local", "dev", "ci", "remote"] = "local"
    mode: Literal["local", "registry"] = "local"
    source_root: Path = Path("..")
    state_dir: Path = Path.home() / ".local/state/pokerlost/platform-local"
    secret_dir: Path = Path.home() / ".local/state/pokerlost/platform-local/secrets"
    http_port: Port = 18080
    https_port: Port = 18443
    prometheus_port: Port = 19090
    grafana_port: Port = 13000
    loki_port: Port = 13100
    alloy_port: Port = 12345
    syslog_port: Port = 15140
    metrics_retention_days: Annotated[int, Field(ge=1, le=30)] = 15
    metrics_retention_mb: Annotated[int, Field(ge=512, le=10240)] = 2048
    logs_retention_days: Annotated[int, Field(ge=1, le=30)] = 7

    @model_validator(mode="after")
    def validate_paths_and_ports(self) -> DeploySettings:
        if "secret_dir" not in self.model_fields_set:
            self.secret_dir = self.state_dir / "secrets"
        ports = [
            getattr(self, name)
            for name in type(self).model_fields
            if name.endswith("_port")
        ]
        if len(ports) != len(set(ports)):
            raise ValueError("Listener ports must be distinct")
        for path in (self.source_root, self.state_dir, self.secret_dir):
            if re.fullmatch(r"[\w./ -]+", str(path)) is None:
                raise ValueError(
                    "Paths must be plain single-line filesystem references"
                )
        sources = self.source_root.resolve()
        owner = Path(__file__).resolve().parents[1]
        for path in (self.state_dir, self.secret_dir):
            if not path.is_absolute() or any(
                path.resolve().is_relative_to(root) for root in (sources, owner)
            ):
                raise ValueError(
                    "State/secrets require absolute paths outside source checkouts"
                )
        return self


def emit_environment(settings: DeploySettings, manifest: Path, output: Path) -> None:
    """Resolve a complete plan before writing output; emit secret references only."""
    data = load_manifest(manifest)
    references: dict[str, str] = {}
    for name, artifact in data["images"].items():
        if settings.mode == "local" and name != "postgres":
            commit = artifact.get("sourceCommit")
            if not commit:
                raise ValueError(
                    f"Local build requires a reviewed sourceCommit: {name}"
                )
            references[name] = (
                artifact["repository"].rsplit("/", 1)[-1] + ":local-" + commit[:12]
            )
            if (epoch := artifact.get("sourceDateEpoch")) is not None:
                references[name] += f"-e{epoch}"
        else:
            references[name] = image_ref(name, artifact, False)
    references.update(data.get("observability", {}))
    if set(data.get("observability", {})) != {"prometheus", "grafana", "loki", "alloy"}:
        raise ValueError("Full startup requires the v2 monitoring inventory")
    lines = [
        f"{name.upper().replace('-', '_')}_IMAGE={ref}"
        for name, ref in references.items()
    ]
    lines += [
        f"{name.upper().replace('-', '_')}_SOURCE_COMMIT={artifact['sourceCommit']}"
        for name, artifact in data["images"].items()
        if artifact.get("sourceCommit")
    ]
    lines += [
        f"{name.upper().replace('-', '_')}_SOURCE_DATE_EPOCH="
        f"{artifact.get('sourceDateEpoch') or 0}"
        for name, artifact in data["images"].items()
        if artifact.get("sourceCommit")
    ]
    values = settings.model_dump(mode="json")
    for name, value in values.items():
        key = name.upper() if name.endswith("_port") else "PLATFORM_" + name.upper()
        lines.append(f"{key}={value}")
    # Named Docker build context contains a bare source-only SDK cache, no credentials.
    lines.append(f"SDK_SOURCE_CONTEXT={settings.state_dir / 'sdk-source'}")
    lines.append(
        f"GAME_ARTIFACT={settings.source_root / 'pokerClient/dist/poker-game-web'}"
    )
    output.mkdir(parents=True, exist_ok=True)
    owner = manifest.parent
    prometheus = yaml.safe_load((owner / "observability/prometheus.yaml").read_text())
    for job in prometheus["scrape_configs"]:
        for target in job.get("static_configs", []):
            target.setdefault("labels", {})["environment"] = settings.environment
    files = {"prometheus.yaml": yaml.safe_dump(prometheus, sort_keys=False)}
    loki = yaml.safe_load((owner / "observability/loki.yaml").read_text())
    loki["limits_config"]["retention_period"] = f"{settings.logs_retention_days * 24}h"
    files["loki.yaml"] = yaml.safe_dump(loki, sort_keys=False)
    files["web-environment.conf"] = (
        "listen 8080;\nserver_name _;\nset $deployment_environment "
        + settings.environment
        + ";\n"
    )
    targets = {
        name: {"loadBalancer": {"servers": [{"url": f"http://{name}:8000"}]}}
        for name in ("auth", "accounts", "virtual-money", "poker", "crypto")
    }
    targets["website"] = {"loadBalancer": {"servers": [{"url": "http://web:8080"}]}}
    files["gateway-upstreams.yaml"] = yaml.safe_dump(
        {"http": {"services": targets}}, sort_keys=False
    )
    dashboard = json.loads((owner / "observability/grafana/dashboard.json").read_text())
    for variable in dashboard["templating"]["list"]:
        if variable["name"] == "environment":
            variable["query"] = settings.environment
            variable["current"] = {
                "text": settings.environment,
                "value": settings.environment,
            }
    files["dashboard.json"] = json.dumps(dashboard, indent=2) + "\n"
    for source, target in (
        ("config.alloy", "alloy.alloy"),
        ("alerts.yaml", "alerts.yaml"),
        ("grafana/datasources.yaml", "grafana-datasources.yaml"),
        ("grafana/dashboards.yaml", "grafana-dashboards.yaml"),
    ):
        files[target] = (owner / "observability" / source).read_text()
    identity = hashlib.sha256()
    for name, content in sorted(files.items()):
        identity.update(name.encode() + b"\0" + content.encode() + b"\0")
    config_sha256 = identity.hexdigest()
    config_dir = output.resolve() / "configs" / config_sha256
    config_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = config_dir / name
        if path.is_symlink() or (path.exists() and path.read_text() != content):
            raise ValueError("Immutable configuration snapshot is damaged")
        if not path.exists():
            path.write_text(content)
            path.chmod(0o644)
    lines.append(f"PLATFORM_CONFIG_DIR={config_dir}")
    (output / "compose.env").write_text("\n".join(lines) + "\n")
    (output / "plan.json").write_text(
        json.dumps(
            {
                "settings": values,
                "compose_keys": sorted(line.partition("=")[0] for line in lines),
                "images": references,
                "game": data["game"],
                "config_dir": str(config_dir),
                "config_sha256": config_sha256,
                "execution": "prepared-only"
                if settings.environment == "remote"
                else "local-compose",
            },
            indent=2,
        )
        + "\n"
    )


app = typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
def main(
    output: Annotated[Path, typer.Option()] = Path(".local/generated"),
    manifest: Annotated[Path, typer.Option()] = Path("artifacts.lock.json"),
    env_file: Annotated[Path | None, typer.Option()] = None,
    mode: Annotated[Literal["local", "registry"] | None, typer.Option()] = None,
    environment: Annotated[
        Literal["local", "dev", "ci", "remote"] | None, typer.Option()
    ] = None,
    secret_dir: Annotated[Path | None, typer.Option()] = None,
    state_dir: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Validate all inputs with no implicit dotenv and no secret values in output."""
    inputs: dict[str, Any] = {
        key: value
        for key, value in {
            "mode": mode,
            "environment": environment,
            "secret_dir": secret_dir,
            "state_dir": state_dir,
        }.items()
        if value is not None
    }
    try:
        settings = DeploySettings(_env_file=env_file, **inputs)
        emit_environment(settings, manifest, output)
    except ValidationError, ValueError, OSError:
        typer.echo(
            "Invalid deployment plan: check paths, ports and artifact pins",
            err=True,
        )
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
