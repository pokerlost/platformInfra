# Release guide

This change prepares development delivery only. Merge, tag, release and production deployment require a separate instruction.

Before an approved release, require green owner source/installed-artifact tests and valid whole-source language coverage reports with advisory percentages, exact private OCI digest provenance, private Actions package access, reviewed owner chart source SHAs, manifest/bootstrap hashes and actual browser/gateway acceptance. Full platform acceptance additionally requires owner-admitted private SDK acquisition, every service image, PostgreSQL migrations, failure recovery, storage retention and verified TLS. A static chart render or preview is not full platform acceptance.

Record actual CI URLs, immutable artifacts, language denominators and remaining blockers in the PR. Do not add runtime excludes, remove defensive guards, accept skipped tests as passing or use a cached test layer to claim fresh execution. Retain only task-owned test logs and synthetic fixtures. Verify package/cache visibility before publication; do not make a package public to solve an Actions access failure.

For rollback, select the previously verified manifest and owner charts, assess schema compatibility, preserve database backups and run native Helm/Compose commands in the explicitly authorized environment. Never automatically downgrade historical migrations or delete storage.
