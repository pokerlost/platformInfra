"""Pure, versioned input schemas for the artifact adapter."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

SERVICES = ("auth", "accounts", "virtual-money", "poker", "crypto")
EXPECTED_IMAGES = {"web", "gateway", "postgres", *SERVICES}
EXPECTED_CHARTS = {"service", "web", "gateway"}
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
ResourceName = Annotated[str, Field(pattern=r"^[a-z](?:[a-z0-9-]{0,43}[a-z0-9])?$")]


class ImageArtifact(BaseModel):
    """Approved immutable reference, with an explicit optional local preview tag."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    repository: Annotated[
        str,
        Field(
            pattern=r"^(?:ghcr\.io/[a-z0-9]+(?:[._-][a-z0-9]+)*/"
            r"[a-z0-9]+(?:[._-][a-z0-9]+)*|postgres)$"
        ),
    ]
    digest: Annotated[str, Field(pattern=r"^(?:sha256:[0-9a-f]{64})?$")] = ""
    source_commit: Commit | None = Field(default=None, alias="sourceCommit")
    source_date_epoch: Annotated[int | None, Field(strict=True, ge=0)] = Field(
        default=None, alias="sourceDateEpoch"
    )
    local_tag: Annotated[str | None, Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")] = Field(
        default=None, alias="localTag"
    )


class VendoredArtifact(BaseModel):
    """Provenance is optional for synthetic fixtures, never inferred from bytes."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    file: str
    sha256: Sha256
    source: str | None = None
    source_commit: Commit | None = Field(default=None, alias="sourceCommit")
    version: str | None = None


class GameArtifact(BaseModel):
    """Stable bridge identity; this schema does not execute or fetch the artifact."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    client_commit: Commit = Field(alias="clientCommit")
    manifest_sha256: Sha256 = Field(alias="manifestSha256")
    bridge_version: Annotated[int, Field(strict=True, ge=1, le=1)] = Field(
        alias="bridgeVersion"
    )
    image: Annotated[
        str | None,
        Field(pattern=r"^ghcr\.io/pokerlost/poker-game-web@sha256:[0-9a-f]{64}$"),
    ] = None


class ArtifactManifest(BaseModel):
    """Versioned inventory; v2 adds a closed, digest-pinned monitoring stack."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    schema_version: Annotated[int, Field(strict=True, ge=1, le=2)] = Field(
        alias="schemaVersion"
    )
    observability: dict[
        str,
        Annotated[
            str,
            Field(
                pattern=r"^(?:prom/prometheus:v[0-9.]+|grafana/grafana:[0-9.]+|grafana/loki:[0-9.]+|grafana/alloy:v[0-9.]+)@sha256:[0-9a-f]{64}$"
            ),
        ],
    ] = Field(default_factory=dict)
    images: dict[str, ImageArtifact]
    charts: dict[str, VendoredArtifact]
    game: GameArtifact
    gateway_api: VendoredArtifact = Field(alias="gatewayApi")

    @model_validator(mode="after")
    def validate_inventory(self) -> ArtifactManifest:
        if set(self.images) != EXPECTED_IMAGES or set(self.charts) != EXPECTED_CHARTS:
            raise ValueError("Unsupported artifact inventory")
        if self.schema_version == 2 and set(self.observability) != {
            "prometheus",
            "grafana",
            "loki",
            "alloy",
        }:
            raise ValueError("Schema v2 requires the complete monitoring inventory")
        if self.schema_version == 1 and self.observability:
            raise ValueError("Monitoring requires schema v2")
        return self


class ResourceNames(BaseModel):
    """Names accepted by both Compose output and Kubernetes values."""

    model_config = ConfigDict(hide_input_in_errors=True)
    release: ResourceName
    namespace: ResourceName
