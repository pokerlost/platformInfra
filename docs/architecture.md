# Architecture

The Vue/TypeScript website serves one immutable Flutter web build produced by the Dart-only pokerClient workspace. Its `make export-web` command uses the pinned Flutter SDK and Dart checksum tool, with no Python template or project environment. The native client and that build use the same Dart contract and Flutter gameplay package. pokerengine remains the authoritative C++ engine with its Python binding; the SDK does not become a second engine. The preview is synthetic and public only. A production gameplay transport is not implemented by infrastructure.

Traefik OSS terminates the gateway and selects the website or one of five foundation HTTP services. Service-specific prefixes are stripped once. Unknown API and realtime requests return an error rather than the SPA. TLS uses an existing certificate Secret in Kubernetes and explicit certificate files in Compose. No dashboard, Docker provider, application-start endpoint or blanket mutation retry is enabled.

`artifacts.lock.json` is the compatibility boundary: immutable images, checksum-verified owner chart packages, client source SHA, Flutter manifest hash and bridge version. `tools/artifacts.py` validates those inputs and writes values. It never runs a shell, Git, Docker, Helm, kubectl or an application. Native Make targets invoke Compose and Helm directly. Source checkout inventory belongs to setupSystem; this repository does not maintain another copy.

The generic service chart belongs to fastApiTemplate, the gateway chart to pokerGateway, and the static website chart to pokerWeb. Refresh packages from a reviewed owner commit, record its full SHA and verify the archive hash. Do not edit a vendored chart in place. Common engineering rules belong to pythonTemplate and CI tool installers to fastApiTemplate.

Only authService and accountsService use PostgreSQL and a migration Job, using the same application image as the service. Other foundation services receive no database configuration. Existing database Secrets are references, not secret values. The bundled PostgreSQL chart is an explicitly local acceptance fixture with retained PVCs, not a production database offering.
