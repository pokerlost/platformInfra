# Local operations and recovery

[Home](../README.md) · [Deployment](deployment.md) · [Observability](observability.md)

Use the same unique Compose project, private settings file and values directory
for each operation. Data volumes, secret files and previous artifact receipts are
separate from configuration and source checkouts. No target runs prune, volume
removal or automatic migration downgrade.

```bash
make up PROJECT=poker-platform-example PLATFORM_ENV_FILE="$local_env"
make restart PROJECT=poker-platform-example PLATFORM_ENV_FILE="$local_env"
make upgrade PROJECT=poker-platform-example PLATFORM_ENV_FILE="$selected_env"
make rollback PROJECT=poker-platform-example PLATFORM_ENV_FILE="$selected_env"
```

Repeated `up` reuses images/storage and runs acceptance again. `restart` restarts
DB/monitoring and re-establishes native application dependencies before acceptance.
`upgrade` records the last accepted env/plan/manifest as rollback inputs, promotes
the selected built images/configuration and only advances the active receipt after
acceptance. Hash-addressed configuration preserves the prior bytes. `rollback`
checks the old image/source receipts, selects the saved native Compose env and
runs acceptance against that saved plan. It does not undo database migrations.
Review schema compatibility before any real application rollback.

## Backup and empty-destination restore

```bash
make backup PROJECT=poker-platform-example PLATFORM_ENV_FILE="$local_env"
make restore PROJECT=poker-platform-example BACKUP_DIR="$backup" RESTORE_PROJECT=poker-platform-restore-example RESTORE_STATE_DIR="$new_private_state"
```

Backup requires the selected profile to match its accepted active receipt. It
pauses applications, takes two logical `pg_dump` archives, stops monitoring for
consistent cold copies of Prometheus/Loki/Grafana data, and records exact image
IDs, manifest, Compose files, owner packages, rendered configuration and five
secret files. It writes SHA-256 checksums into a new timestamped private directory
under the external state root. Its exit trap resumes the full profile and repeats
acceptance; failure is reported. The archive contains credentials and personal
operational metadata: keep it private and protect any exported copy.

Restore verifies checksums and exact locally available image IDs before creating
data. It refuses an existing destination state, containers or volumes. It creates
a new `poker-platform-restore-*` project with separate volumes and private secrets,
restores both databases using native PostgreSQL tools, restores cold monitoring
data and runs the full acceptance suite. Default listener offset is 1000; choose
another non-colliding `RESTORE_PORT_OFFSET` explicitly when needed.
The source project and volumes are preserved. This is a same-daemon recovery path:
image layers are not inside the backup. On another daemon first load verified
image archives or acquire the pinned images using the approved connection.
A matching tag with different image bytes is rejected.

## Troubleshooting

| Symptom | Check and action |
| --- | --- |
| Config fails before startup | Paths must be absolute outside sources; ports distinct; replace placeholders; inspect plan references |
| Source/image receipt mismatch | Use the manifest's exact clean checkout and rerun build-or-reuse; do not relabel another build |
| Missing registry digest/read access | Use the verified local source/cache path; do not invent a digest or widen package access |
| Gateway startup health fails | Read its JSON logs and health history; Yaegi initialization under CPU pressure can delay readiness; do not start browser checks concurrently with builds |
| UI fails to load | Check the real client manifest/file hashes, static MIME/cache and gateway routing; preserve the Playwright trace |
| No metrics/logs | Inspect local datasource health, scrape targets and Alloy; run accept-local and inspect coverage/observability.json |
| Readiness false | Check DB TCP health and migration revision, independently of process liveness |
| Restore rejects a target | Choose a new empty project/state; never remove an existing volume to satisfy the check |
| Loki disk pressure | Retention is time based; provision an owner-approved quota-backed filesystem before claiming a hard disk bound |

Monitoring is best effort and never a business dependency. UDP logging is bounded
and nonblocking; an outage may lose logs. Do not claim lossless delivery. Local
HTTP and synthetic technical checks do not establish production TLS, gameplay,
payment or durability guarantees.

To restart a restored project, select its saved values directory/settings and archived manifest with PLATFORM_VALUES_DIR, PLATFORM_ENV_FILE and PIN_MANIFEST. The same native up/down commands then use the selected artifact receipts; PIN_MANIFEST defaults to the repository lock. Retain the archived manifest's adjacent owner packages/config inputs.
