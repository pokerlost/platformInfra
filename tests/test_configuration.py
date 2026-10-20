"""Verify native Compose/Helm boundaries and retention without invented services."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_preview_has_only_real_edge_components_and_valid_tmpfs() -> None:
    base = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert set(base["services"]) == {"web", "gateway"}
    for service in base["services"].values():
        assert service["read_only"] and service["cap_drop"] == ["ALL"]
        assert service["tmpfs"] and all(
            path.startswith("/") for path in service["tmpfs"]
        )
        assert "docker.sock" not in str(service)
    assert all(
        port.startswith("127.0.0.1:") for port in base["services"]["gateway"]["ports"]
    )
    assert (
        base["networks"]["edge"]["internal"]
        and base["networks"]["foundation"]["internal"]
    )
    assert base["services"]["web"]["networks"] == ["edge"]
    assert "ingress" in base["services"]["gateway"]["networks"]


def test_database_migrations_and_storage_belong_only_to_database_services() -> None:
    data = yaml.safe_load((ROOT / "compose.foundation.yaml").read_text())
    services = data["services"]
    for name in ["auth", "accounts"]:
        migration = services[name + "-migrate"]
        assert migration["image"] == services[name]["image"]
        assert migration["command"] == ["python", "-m", "alembic", "upgrade", "head"]
        assert (
            services[name]["depends_on"][name + "-migrate"]["condition"]
            == "service_completed_successfully"
        )
        assert services[name + "-db"]["volumes"] == [
            name + "_data:/var/lib/postgresql/data"
        ]
    for name in ["virtual-money", "poker", "crypto"]:
        assert "env_file" not in services[name] and "depends_on" not in services[name]
    assert set(data["volumes"]) == {"auth_data", "accounts_data"}
    for service in services.values():
        assert "ports" not in service
    makefile = (ROOT / "Makefile").read_text()
    assert "down --remove-orphans" not in makefile and "down --volumes" not in makefile
    assert "--kubeconfig $(LOCAL_KUBECONFIG)" in makefile
    assert "Remote cluster forbidden" in makefile
