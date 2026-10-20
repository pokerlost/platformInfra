# Version compatibility

[Home](../README.md) · [Architecture](architecture.md)

Infrastructure is a versioned development composition. `VERSION` is its canonical
SemVer source (initially `0.1.0-dev.0`); verification tooling keeps its separate
`pyproject.toml` version. `make build` exports the exact clean Git source as
`dist/platform-infra-<version>.tar.gz`; the archived compatibility manifest binds
all component, chart and image pins to that composition version.
`artifacts.lock.json` schema 2 records eight image inputs, four official monitoring
images, three owner chart packages, Gateway API CRDs and Flutter bridge/artifact
identity. Source commits, image IDs, registry digests and chart hashes are distinct.

Local mode derives stable tags from the full reviewed source pins and verifies
OCI source labels before up. A local image ID is never written as a registry
digest. Registry mode requires every actual immutable image digest and existing
read authorization. Six application digests are currently intentionally empty;
this blocks registry mode while the full local build mode remains usable. The gateway entry is the actual reviewed private OCI promotion, not a local config ID.

The client entry pins bridge 1, a full client commit and the manifest checksum of
the actual published bundle. A locally rebuilt Flutter bundle may have a different
build ID and must not be silently substituted. Owner chart archives are immutable:
a chart source may predate a later Docker/Go-only fix when its packaged bytes are
unchanged. Preserve the owner full source and exact archive checksum.

Update in dependency order: template owners -> SDK/engine -> consumers ->
web/gateway -> this manifest. Inspect migrations and compatibility, build/test the
exact source, advance explicit pins, then use native upgrade/rollback with saved
receipts. Do not repackage an existing chart version, overwrite released artifacts,
rewrite refs or confuse an application rollback with a schema downgrade.

Local build inputs also record web/gateway commit timestamps as sourceDateEpoch. Compose passes it to native BuildKit; the preflight verifies it against the exact Git commit. New web/gateway local tags include the epoch, preserving earlier wall-clock-built tags and backup image receipts. Legacy archived manifests without this optional field remain readable (epoch zero); they are not silently rewritten.

## Local verification and release readiness

`make version` reads the native version owners. `make ci-local` executes the
repository's native quality/build/acceptance targets once, then checks artifact
versions. No GitHub token or Actions API is required. Dependency preparation may
need the existing package/image access; `OFFLINE=1` requires prepared inputs and
fails as blocked when they are unavailable. BuildKit caches dependencies and build
layers, while tests execute freshly. `make coverage` reads the current result and
never reruns the suite. Coverage below 100% is advisory.

`coverage/ci-local.json` records schema 1, source commit/dirty/content SHA-256,
commands and exits, native tool versions, artifact hashes/versions and timestamps.
`coverage/ci-local-summary.md` and `coverage/artifacts.json` are supporting reports;
`coverage/summary.md` remains the coverage report. Ignored build outputs remain in
`dist/`. A source or lock change invalidates previous evidence. A failed or blocked
run must not leave a successful current receipt. Local CI does not replace hosted
mandatory checks or authorize a merge when those checks are billing-blocked.

Choose a version bump from the actual compatibility effect, update its native
metadata/lock/chart relationship and changelog, and run local CI on the exact
reviewed source. Quality/documentation-only work keeps current prerelease versions.
A clean integrated `main` with successful mandatory checks can receive an annotated
`v<application-version>` tag (or `chart/v<chart-version>` for an independent chart),
after inspecting tag-triggered workflows and confirming explicit task authority.
Tags, releases, package publication and deployment are separate operations; the
commands above do none of them. Never retag a published artifact or infer a registry
digest from a local Docker image ID.

`make verify` validates Compose inputs and executes the same native disposable Kind
PostgreSQL acceptance used by hosted CI. It requires the pinned Kind, Helm, kubectl,
Docker and uv tools on the host. It creates only a uniquely named
`poker-platform-ci-*` cluster, synthetic Secrets and owned temporary resources,
then removes that cluster. Existing application containers, data volumes and
kubeconfigs are untouched. Runtime `up`, restart and production deployment are not
part of local CI. The default `ci-local` includes this database acceptance; hosted
jobs may select the documented static/build subset and run `test-database-local`
separately, with both jobs required.
