# Version compatibility

[Home](../README.md) · [Architecture](architecture.md)

Infrastructure is development composition; no release/tag is created here.
`artifacts.lock.json` schema 2 records eight image inputs, four official monitoring
images, three owner chart packages, Gateway API CRDs and Flutter bridge/artifact
identity. Source commits, image IDs, registry digests and chart hashes are distinct.

Local mode derives stable tags from the full reviewed source pins and verifies
OCI source labels before up. A local image ID is never written as a registry
digest. Registry mode requires every actual immutable image digest and existing
read authorization. Seven application digests are currently intentionally empty;
this blocks registry mode while the full local build mode remains usable.

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
