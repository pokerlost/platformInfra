# Local deployment and recovery

Docker Compose v2 owns local composition. Build the exact website and gateway images in their owner repositories before preview startup. The manifest's explicit local tags apply only to preview. `make up` requires all immutable image references before creating credentials or containers; there are no placeholder backend images.

```sh
make preview PROJECT=poker-platform-example
make status PROJECT=poker-platform-example
make logs PROJECT=poker-platform-example
PLATFORM_TEST_URL=http://127.0.0.1:18080 make test-integration
make down PROJECT=poker-platform-example
```

Only the gateway joins the externally connected ingress network and binds loopback ports 18080/18443. Website and backend networks are internal. Containers use read-only filesystems, dropped capabilities and bounded writable temporary mounts. Compose foundation startup orders healthy databases, one-shot migrations, then APIs. A failed migration prevents service startup. `down` preserves named database volumes; no default target deletes storage.

Kubernetes execution is restricted to a disposable Kind cluster named `poker-platform-*`. Use the pinned Helm, Kind and kubectl versions in `.github/actions/deployment-tools/action.yml`. Choose a unique name and an explicit private kubeconfig:

```sh
make cluster CLUSTER_NAME=poker-platform-example
kind load docker-image pokerweb:EXACT_LOCAL_TAG pokergateway:EXACT_LOCAL_TAG --name poker-platform-example
make deploy-preview CLUSTER_NAME=poker-platform-example
```

Every deploy target obtains the named Kind kubeconfig and checks its API server is loopback. It does not use the user's current remote context. Gateway API CRDs are vendored and checksum verified. Preview uses a NodePort gateway, two website replicas, probes, a PDB, resource limits and no service-account token in workloads. Default Kind does not enforce NetworkPolicy; declarative policy alone is not evidence of network isolation.

Once every private application digest is present, `make deploy-local CLUSTER_NAME=...` installs local PostgreSQL, same-image migration Jobs and the five APIs before website/gateway. `make kube-secrets` creates technical local credentials only; never point it at production. TLS is configured through the gateway owner's chart and an existing certificate Secret. Certificate issuance, DNS, external load balancers and remote clusters are not provisioned here.

Before recovery, preserve the current artifact lock, `helm history`, workload status and database backup. Roll back to a previously verified immutable image/chart set with Helm; never assume a schema downgrade is data safe. Website rollout and replica changes do not recreate database PVCs. `make undeploy-local CLUSTER_NAME=...` retains PVCs and Secrets. The local PostgreSQL chart explicitly retains claims after uninstall and scale-down. Deleting an entire disposable Kind cluster removes its local storage, so export acceptance evidence first. No production recovery claim follows from a disposable local fixture.

Keep replica changes in Helm values. With Helm 4 server-side apply, an unrelated `kubectl scale` manager can conflict with later upgrades. Resolve ownership explicitly on the affected local Deployment before continuing; do not enable force replacement or force conflicts globally. Runtime acceptance includes an intentionally unavailable image, observed readiness failure and Helm rollback to the previous working image.
