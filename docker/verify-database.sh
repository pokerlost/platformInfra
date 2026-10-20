#!/bin/bash
# Native local counterpart of the required PostgreSQL Helm acceptance job.
set -euo pipefail
for tool in docker kind kubectl helm; do command -v "$tool" >/dev/null; done
mkdir -p coverage .local
{
  kind version
  helm version --short
  kubectl version --client
} > coverage/database-tools.txt
cluster="poker-platform-ci-$(date +%s)-$$"
work=$(mktemp -d "${TMPDIR:-/tmp}/poker-platform-ci.XXXXXX")
config="$work/kubeconfig"
created=0
cleanup() {
  status=$?
  trap - EXIT INT TERM
  if [ "$created" = 1 ]; then kind delete cluster --name "$cluster"; fi
  rm -rf -- "$work"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
postgres='postgres:17.11-trixie@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3'
node='kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5'
for image in "$postgres" "$node"; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    if [ "${OFFLINE:-0}" = 1 ]; then echo "Required offline image unavailable: $image" >&2; exit 2; fi
    docker pull "$image"
  fi
done
alias='foundation-postgres:local-2d2b8998d310'
if docker image inspect "$alias" >/dev/null 2>&1; then
  test "$(docker image inspect "$alias" --format '{{.Id}}')" = "$(docker image inspect "$postgres" --format '{{.Id}}')"
else
  docker tag "$postgres" "$alias"
fi
# Set before create so a partial task-owned cluster is cleaned on failure too.
created=1
kind create cluster --name "$cluster" --image "$node" --kubeconfig "$config" --wait 120s
kind load docker-image "$alias" --name "$cluster"
kubectl --kubeconfig "$config" --context "kind-$cluster" create namespace foundation
PLATFORM_SOURCE_ROOT="$work/sources" make kube-secrets \
  CLUSTER_NAME="$cluster" LOCAL_KUBECONFIG="$config" PROJECT="$cluster" \
  PLATFORM_VALUES_DIR="$work/values" PLATFORM_STATE_DIR="$work/state" \
  PLATFORM_SECRET_DIR="$work/secrets" PLATFORM_ENV_FILE=
helm upgrade --install platform-databases deploy/local-postgres --kubeconfig "$config" --kube-context "kind-$cluster" --namespace foundation --set localDevelopment=true --set image="$alias" --wait --timeout 180s
PLATFORM_TEST_KIND_NAME="$cluster" PLATFORM_TEST_KUBECONFIG="$config" make test-database
