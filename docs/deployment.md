# Clean checkout and local deployment

[Home](../README.md) · [Architecture](architecture.md) · [Operations](operations.md)

## Prerequisites

Linux Docker/BuildKit and Compose with named build contexts, Git, Make, Bash, jq,
OpenSSL, uv 0.12.15 and Python 3.14.7 are used by the verified local path. The
acceptance environment used Docker 29.7.2 and Compose 5.5.0. Helm 4.3.1, Kind
0.33.0 and kubectl 1.37.0 are only needed for chart/Kind checks; their official
URLs and checksums are in `.github/actions/deployment-tools/action.yml`.
Use an existing authorized GitHub connection for private sources/artifacts.
No token belongs in a clone URL, dotenv file, build argument or artifact.

Clone this repo and choose a new private workspace for seven clean sibling
checkouts. Do not switch or clean someone else's worktree. From this repo root,
with `PLATFORM_SOURCE_ROOT` pointing to that workspace, the native preparation is:

```bash
for entry in web:pokerWeb gateway:pokerGateway auth:authService accounts:accountsService virtual-money:virtualMoney poker:pokerService crypto:cryptoService; do
  key=${entry%%:*}
  repo=${entry#*:}
  git clone --no-checkout "https://github.com/pokerlost/$repo.git" "$PLATFORM_SOURCE_ROOT/$repo"
  git -C "$PLATFORM_SOURCE_ROOT/$repo" checkout --detach "$(jq -r --arg key "$key" '.images[$key].sourceCommit' artifacts.lock.json)"
done
```

All seven checkouts must have the exact manifest `sourceCommit` and a clean Git
status. The build target checks both before creating secrets or building.
Accounts Git is currently `pokerlost/accountsService`; the legacy package namespace
`ghcr.io/mloso/accountsservice` is preserved until its owner approves a migration.

## Client artifact and SDK cache

The game artifact is the published source `0b68c815be0cf69c3722e3bd74fc96950ca455b9`,
bridge 1, manifest SHA-256
`7f6e2ce2f53734c00d10e6690cec5f11d95b77328921394c04c4ab0021bbe417`.
The private OCI digest is recorded in `artifacts.lock.json`. With an existing
package-read connection, native `docker pull`, `docker create`, and `docker cp`
export `/` from that scratch image into
`$PLATFORM_SOURCE_ROOT/pokerClient/dist/poker-game-web`. Remove only the created
export container. Never assume a fresh source rebuild is byte-identical to the
published bundle: Flutter build IDs can differ. The real CI artifact from
[pokerClient run 39343287357](https://github.com/pokerlost/pokerClient/actions/runs/39343287357)
was the alternative actually downloaded and checksum-verified for this acceptance.
Actions artifacts expire after 14 days; the pinned private OCI requires its
existing read connection after expiry. The website's native installer verifies
all manifest file checksums and bridge compatibility before bundling.

Prepare a source-only bare SDK cache outside all checkouts. Its objects must
include the SDK commit pinned by the five service locks:

```bash
install -d -m 700 "$private_state/sdk-source"
git clone --bare https://github.com/pokerlost/pypokerlost.git "$private_state/sdk-source/pypokerlost.git"
git -C "$private_state/sdk-source/pypokerlost.git" cat-file -t c4d8327e8318eab6769b3f05c4a7d848c75afb0b
```

The Docker named context contains only that source cache, with no credentials.
Native uv/Git resolves the existing lock against it during build. Only the installed
runtime venv crosses into the final service image; source cache, Git and uv do not.
B1's remote build continues to use the existing SDK-only short-lived App connection.

## Configure and start

Copy [.env.example](../.env.example) to a private external file. Set absolute
`PLATFORM_SOURCE_ROOT`, `PLATFORM_STATE_DIR` and `PLATFORM_SECRET_DIR`; choose
unused loopback ports and a unique `poker-platform-*` Compose project name.
The state root contains the SDK cache above. `local_env` below names that file,
not its contents. No implicit `.env` is loaded by the settings adapter.

```bash
make config validate plan PLATFORM_ENV_FILE="$local_env"
make build-or-reuse PLATFORM_ENV_FILE="$local_env"
make up PROJECT=poker-platform-example PLATFORM_ENV_FILE="$local_env"
make status PROJECT=poker-platform-example
make accept-local
make logs PROJECT=poker-platform-example
make down PROJECT=poker-platform-example
```

Settings priority is explicit CLI options > `PLATFORM_*` environment > the
selected dotenv > defaults. Omitted CLI options do not overwrite environment.
Make command-line state/secret paths are forwarded as explicit CLI options.
`main`, `dev`, `test` and `local` select runtime identity. Legacy `ci`/`remote`
environment values now fail with a configuration error; explicitly select `execution=ci/remote`
separately. Only environment local with non-remote execution can administer Compose; other
environments prepare a plan
and refuses local side effects. `local` image mode builds exact pinned sources;
`registry` image mode requires every immutable image digest before startup.
Generated Compose variables are cleared from the ambient Compose process so its
selected env file, including a rollback selection, remains authoritative.

`config` validates everything first and emits `compose.env`, `plan.json` and
immutable hash-addressed config snapshots under `.local/generated`. Those files
contain secret references only. `validate` runs Compose's native config check
without resolving secret env files. `plan` lists selected services/images without
starting them. `build-or-reuse` uses native BuildKit caching. `up` never builds:
it verifies image/source receipts, initializes missing local credentials, runs
healthy DB -> migrations -> APIs and monitoring, then executes real acceptance.
A failed acceptance does not advance the active receipt. `status` and `down`
use the most recently selected generated plan. `down` never removes volumes.

Default URLs are edge `127.0.0.1:18080`, Grafana `127.0.0.1:13000`, Prometheus
`127.0.0.1:19090`, Loki `127.0.0.1:13100`, Alloy `127.0.0.1:12345` and UDP syslog
`127.0.0.1:15140`. Grafana user is `operator`; its generated password is the private
file `PLATFORM_SECRET_DIR/grafana-admin-password`. Do not print or commit it.
The ordinary local profile is HTTP on loopback. HTTPS requires explicitly supplied
certificate files/Secret and a separately reviewed trust model.

## Disposable Kubernetes

Compose above is the full local entrypoint. Helm checks use the checksum-verified
owner packages in the manifest and the vendored Gateway API CRDs. Use a fresh
private kubeconfig, a uniquely named `poker-platform-*` Kind cluster, and the pinned
native tools. Never use an ambient remote context. `make deploy-kind` is an
explicit local Helm path after all seven image refs and database secrets have
been prepared; it does not install the Compose monitoring profile into Kubernetes.
`undeploy-local` retains database PVCs and Secrets. Deleting a disposable Kind
cluster deletes its local storage, so export its evidence first. Default Kind
without a policy-enforcing CNI does not prove NetworkPolicy isolation.

Native local builds forward existing HTTP_PROXY/HTTPS_PROXY/NO_PROXY through BuildKit's predefined proxy arguments without writing their values to the plan. These arguments are excluded from normal cache/history by BuildKit; no proxy credential or new connection is provisioned. Direct loopback acceptance uses trust_env=False.

## Private application image export/load

The native alternative to rebuilding seven private applications is a verified
private image bundle. After an accepted build, choose a new external directory:

```bash
make export-images PLATFORM_ENV_FILE="$local_env" IMAGE_BUNDLE_DIR="$new_private_bundle"
make load-images PLATFORM_ENV_FILE="$local_env" IMAGE_BUNDLE_DIR="$bundle" PIN_MANIFEST="$bundle/artifacts.lock.json"
make up PROJECT=poker-platform-example PLATFORM_ENV_FILE="$local_env" PIN_MANIFEST="$bundle/artifacts.lock.json"
```

The bundle includes seven ready application images, their exact config IDs,
manifest, adjacent owner packages/configuration and file checksums. It contains no
runtime volumes or secret files and is still private source-derived material.
Load validates all checksums and every image ID/source receipt; it does not build
or require private registry pull credentials. Pinned official PostgreSQL and four
monitoring images must already be cached or pulled from their public upstreams.
This is not a claim of an offline cold-daemon acceptance. Source checkouts and the
SDK source cache are needed only for build-or-reuse, not for loaded-artifact up.

The reviewed gateway archive was promoted by [delivery run 39364837277](https://github.com/pokerlost/pokerGateway/actions/runs/39364837277) without rebuilding. Its actual private OCI digest is in the lock. The web package was not visible through either connected Chrome or the package API; no new destination or package access was created. The remaining six private image refs and a local private-pull connection still block registry mode, independently of working local build/load.


## Environment migration

`--environment main|dev|test|local` is separate from `--execution host|ci|remote` and
artifact `--mode local|registry`. There is no implicit ci-to-test or remote-to-main migration.
CLI values override process variables, an explicitly selected dotenv file and defaults. Use
`python -m tools.environment --environment test --dry-run` in the prepared tools environment
for a data-only plan; it creates no files, containers or network requests.

The local state path and existing volumes are preserved. Non-local defaults use distinct
`platform-<environment>` directories and secrets within that directory; an explicit shared path
is rejected. Plans include distinct Compose, namespace and database identities. Non-local
execution remains prepared-only, so changing a label cannot operate the existing local stack.
Select distinct volumes/secrets/credentials when a future explicitly authorized deployment is
implemented; no current data is renamed or migrated. Remote API origins remain not_configured
until supplied explicitly as HTTPS roots. No DNS/remote environment is claimed to exist.

Host SDK clients use the published loopback gateway port. Internal gateway-to-service HTTP remains
an explicitly configured fixed container-network mapping, not a general SDK HTTP exception.
