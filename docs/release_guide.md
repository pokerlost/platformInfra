# Delivery boundaries

[Home](../README.md) · [Versioning](versioning.md) · [Operations](operations.md)

Checks, installed-artifact tests, build, artifacts, publish and deploy are separate
stages. BuildKit caches use target/platform/trust scopes; test results execute
fresh. Secret values never form cache keys or artifact contents. Exact tested
image IDs/source receipts gate promotion; deployment selects built artifacts and
does not rebuild. The SDK App remains SDK-only read and short lived, with exact
reviewed-source/trusted-workflow admission and no dependency on an open PR 1.

Current task permission covers reviewed commits/PR/merge and existing agreed
private artifact destinations. It does not permit a new registry namespace/ACL,
App expansion, release/tag, external DNS/listener or production deployment.
Keep private code/images private. Missing private pull access is a precise blocker
for registry mode, not a reason to widen access or fake a digest.

Before any later release require current source/installed-wheel checks, real
proxy/browser acceptance, valid coverage reports (percentages warn), actual
manifest/image/chart/bridge identities, DB migration/recovery evidence and real
Prometheus/Loki/Grafana data. Local HTTP and technical fixtures do not establish
production TLS, gameplay or payments. Preserve old refs, backup and rollback
artifacts. Cleanup only task-owned ephemeral resources; never prune shared data.
