# Version compatibility

Infrastructure candidate version is `0.1.0.dev0`; the local PostgreSQL chart is independently `0.1.0-dev.0`. No release or tag is created by this task.

Compatibility is pinned in `artifacts.lock.json`, not inferred from matching version strings. Each image uses an immutable digest, each owner chart and Gateway API CRD has a SHA-256, and the Flutter entry pins bridge version 1, its full client commit and manifest SHA. Explicit local preview tags do not replace immutable release inputs. A missing digest blocks full startup before side effects.

Update contracts in dependency order: template owners, SDK/engine as applicable, service/client consumers, website/gateway artifacts, then this manifest. Review migration compatibility and each owner PR before advancing a pin. Public package APIs, SDK generator/manifest schemas, database migration histories, gameplay bridge and Helm chart versions are separate contracts.
