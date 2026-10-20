ifeq ($(OFFLINE),1)
export UV_OFFLINE := 1
endif
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
ifneq ($(CONTAINERIZED),1)
QUALITY_DIST_MOUNT = --mount "type=bind,source=$(CURDIR)/dist,target=/app/dist,readonly"
QUALITY_IMAGE := platforminfra:quality
RUNTIME_IMAGE := platforminfra:candidate
COVERAGE_REPORT := coverage/python/coverage.json
QUALITY_EXTRA_TARGETS := test-integration test-database chart-check check-manifest
.PHONY: kube-secrets cluster local-context gateway-api deploy-kind
kube-secrets cluster local-context gateway-api deploy-kind:
	$(MAKE) CONTAINERIZED=1 $@
VALUES_OUTPUT ?= $(CURDIR)/.local/helm
QUALITY_RUN_ARGS += --mount "type=bind,source=$(VALUES_OUTPUT),target=/app/.local/helm" --env PLATFORM_TEST_URL
# Data-only tests have no sibling checkout mount inside the quality container.
QUALITY_RUN_ARGS += --env PLATFORM_SOURCE_ROOT=/source-checkouts
.PHONY: prepare-values
prepare-values:
	@mkdir -p "$(VALUES_OUTPUT)" dist
quality-image: prepare-values
test-integration test-database: QUALITY_NETWORK := host
test-database: QUALITY_RUN_ARGS += --mount "type=bind,source=$(PLATFORM_TEST_KUBECONFIG),target=/checks/kubeconfig,readonly" --env PLATFORM_TEST_KIND_NAME --env PLATFORM_TEST_KUBECONFIG=/checks/kubeconfig --env PLATFORM_TEST_KUBE_CACHE_DIR=/tmp/platform-kube-cache

COMPOSITION_VERSION = $(shell cat VERSION)
BUILD_COMMAND = test -z "$$(git status --porcelain)" && mkdir -p dist coverage && git archive --format=tar --prefix=platform-infra-$(COMPOSITION_VERSION)/ HEAD | gzip --no-name > dist/platform-infra-$(COMPOSITION_VERSION).tar.gz && git rev-parse HEAD > coverage/composition-source.txt
IMAGE_COMMAND = printf "%s\n" "notApplicable: Compose/Helm consume existing verified images"
VERIFY_COMMAND = $(MAKE) config-check test-database-local
BUILD_RECEIPT_COMMAND := true
VERSION_COMMAND = $(QUALITY_RUN) python -m tools.composition_version version
RELEASE_CHECK_COMMAND = test "$$(sha256sum dist/platform-infra-$(COMPOSITION_VERSION).tar.gz | cut -d " " -f 1)" = "$$(git archive --format=tar --prefix=platform-infra-$(COMPOSITION_VERSION)/ HEAD | gzip --no-name | sha256sum | cut -d " " -f 1)" && $(QUALITY_RUN) python -m tools.composition_version release-check
RECEIPT_COMMAND = $(QUALITY_RUN) python docker/release.py receipt
OFFLINE_PREFLIGHT_COMMAND = command -v kind helm kubectl >/dev/null && $(DOCKER) image inspect postgres:17.11-trixie@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3 kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5 >/dev/null || { echo "BLOCKED: prepare pinned database/Kind images and tools online first." >&2; exit 2; }
CI_LOCAL_TARGETS := check coverage build verify release-check
include docker/quality-python.mk

.PHONY: native-prerequisites
help: native-prerequisites
native-prerequisites:
	@printf '%s\n' 'Infra acceptance also requires host uv, kind, kubectl and Helm; it creates and removes its own local Kind cluster.'
.PHONY: test-database-local
test-database-local:
	/bin/bash docker/verify-database.sh

else
.DEFAULT_GOAL := help
UV ?= uv
DOCKER ?= docker
HELM ?= helm
KIND ?= kind
KUBECTL ?= kubectl
PROJECT ?= poker-platform-local
RELEASE ?= platform
NAMESPACE ?= foundation
CLUSTER_NAME ?= poker-platform-local
VALUES_DIR := .local/helm
LOCAL_KUBECONFIG := $(CURDIR)/.local/kubeconfig
COMPOSE := $(DOCKER) compose --project-name $(PROJECT) --file compose.yaml --env-file $(VALUES_DIR)/compose.env
HELM_LOCAL := $(HELM) --kubeconfig $(LOCAL_KUBECONFIG) --kube-context kind-$(CLUSTER_NAME)
KUBE_LOCAL := $(KUBECTL) --kubeconfig $(LOCAL_KUBECONFIG) --context kind-$(CLUSTER_NAME)
HELM_FLAGS := --namespace $(NAMESPACE) --wait --timeout 180s --rollback-on-failure
.PHONY: help install lint typecheck test-unit test-integration test-database test check values preview-values up preview down status logs init-local cluster local-context gateway-api deploy-preview deploy-local kube-secrets undeploy-local
help:
	@echo "install lint typecheck test test-integration test-database check preview up down status logs cluster deploy-preview deploy-local undeploy-local"
install:
	$(UV) sync --locked
lint:
	$(UV) run --locked ruff check tools tests
	$(UV) run --locked ruff format --check tools tests
typecheck:
	$(UV) run --locked mypy
test-unit:
	$(UV) run --locked pytest --junitxml=coverage/unit.xml --cov --cov-report=term-missing --cov-report=json --cov-report=xml
test: test-unit
test-integration:
	$(UV) run --locked pytest tests/platform_integration.py --junitxml=coverage/platform.xml
test-database:
	$(UV) run --locked pytest tests/postgres_integration.py --junitxml=coverage/postgres.xml
check: lint typecheck test-unit chart-check check-manifest
values:
	$(UV) run --locked python -m tools.artifacts --output $(VALUES_DIR) --release $(RELEASE) --namespace $(NAMESPACE)
preview-values:
	$(UV) run --locked python -m tools.artifacts --output $(VALUES_DIR) --preview --release $(RELEASE) --namespace $(NAMESPACE)
cluster:
	@case '$(CLUSTER_NAME)' in poker-platform-*) ;; *) echo 'Only an explicit local poker-platform-* Kind cluster is allowed'; exit 1;; esac
	@install -d -m 700 .local
	$(KIND) create cluster --name $(CLUSTER_NAME) --image kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5 --kubeconfig $(LOCAL_KUBECONFIG) --wait 120s
local-context:
	@case '$(CLUSTER_NAME)' in poker-platform-*) ;; *) echo 'Only an explicit local poker-platform-* Kind cluster is allowed'; exit 1;; esac
	@umask 077; $(KIND) get kubeconfig --name $(CLUSTER_NAME) > $(LOCAL_KUBECONFIG)
	@chmod 600 $(LOCAL_KUBECONFIG)
	@case "$$($(KUBE_LOCAL) config view --minify -o 'jsonpath={.clusters[0].cluster.server}')" in https://127.0.0.1:*|https://localhost:*) ;; *) echo 'Remote cluster forbidden'; exit 1;; esac
gateway-api: local-context
	$(KUBE_LOCAL) apply -f deploy/crds/gateway-api-v1.6.3.yaml
	$(KUBE_LOCAL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBE_LOCAL) apply -f -
deploy-preview: gateway-api
	$(HELM_LOCAL) upgrade --install $(RELEASE)-web $(VALUES_DIR)/charts/web.tgz --values $(VALUES_DIR)/web.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-gateway $(VALUES_DIR)/charts/gateway.tgz --values $(VALUES_DIR)/gateway.values.json $(HELM_FLAGS)
deploy-kind: gateway-api
	$(MAKE) kube-secrets
	$(HELM_LOCAL) upgrade --install $(RELEASE)-databases deploy/local-postgres --values $(VALUES_DIR)/postgres.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-auth $(VALUES_DIR)/charts/service.tgz --values $(VALUES_DIR)/auth.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-accounts $(VALUES_DIR)/charts/service.tgz --values $(VALUES_DIR)/accounts.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-virtual-money $(VALUES_DIR)/charts/service.tgz --values $(VALUES_DIR)/virtual-money.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-poker $(VALUES_DIR)/charts/service.tgz --values $(VALUES_DIR)/poker.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-crypto $(VALUES_DIR)/charts/service.tgz --values $(VALUES_DIR)/crypto.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-web $(VALUES_DIR)/charts/web.tgz --values $(VALUES_DIR)/web.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-gateway $(VALUES_DIR)/charts/gateway.tgz --values $(VALUES_DIR)/gateway.values.json $(HELM_FLAGS)
kube-secrets: init-local local-context
	@set -eu; umask 077; for name in auth accounts; do \
		sed "s/@$$name-db:5432/@$(RELEASE)-$$name-db:5432/" "$(DEPLOY_SECRET_DIR)/$$name.env" > "$(DEPLOY_SECRET_DIR)/$$name.k8s.env"; \
		sed 's/^DATABASE_URL=//' "$(DEPLOY_SECRET_DIR)/$$name.k8s.env" | tr -d '\n' > "$(DEPLOY_SECRET_DIR)/$$name-database-url"; \
		$(KUBE_LOCAL) create secret generic $(RELEASE)-$$name-database --namespace $(NAMESPACE) --from-file=DATABASE_URL="$(DEPLOY_SECRET_DIR)/$$name-database-url" --from-file=POSTGRES_PASSWORD="$(DEPLOY_SECRET_DIR)/$$name-db-password" --dry-run=client -o yaml | $(KUBE_LOCAL) apply -f -; \
	done
undeploy-local: local-context
	$(HELM_LOCAL) uninstall $(RELEASE)-gateway $(RELEASE)-web $(RELEASE)-auth $(RELEASE)-accounts $(RELEASE)-virtual-money $(RELEASE)-poker $(RELEASE)-crypto $(RELEASE)-databases --namespace $(NAMESPACE) --ignore-not-found --wait
	@echo "Database PVCs and existing Secrets are retained."

.PHONY: check-manifest chart-check config-check
check-manifest:
	$(UV) run --locked python -c "from tools.artifacts import load_manifest; from pathlib import Path; load_manifest(Path('artifacts.lock.json'))"
chart-check: preview-values
	$(HELM) lint $(VALUES_DIR)/charts/web.tgz --strict --values $(VALUES_DIR)/web.values.json
	$(HELM) lint $(VALUES_DIR)/charts/gateway.tgz --strict --values $(VALUES_DIR)/gateway.values.json
	$(HELM) lint deploy/local-postgres --strict --set localDevelopment=true --set image=postgres@sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3

endif

# Native full local Compose lifecycle. State and secrets are external references.
UV ?= uv
DOCKER ?= docker
PROJECT ?= poker-platform-local
PLATFORM_VALUES_DIR ?= $(CURDIR)/.local/generated
PLATFORM_STATE_DIR ?= $(HOME)/.local/state/pokerlost/$(PROJECT)
PLATFORM_SECRET_DIR ?= $(PLATFORM_STATE_DIR)/secrets
PLATFORM_ENV_FILE ?=
DEPLOY_STATE_DIR = $(shell jq -r .settings.state_dir "$(PLATFORM_VALUES_DIR)/plan.json")
DEPLOY_SECRET_DIR = $(shell jq -r .settings.secret_dir "$(PLATFORM_VALUES_DIR)/plan.json")
SETTINGS_CLI = $(if $(filter command line,$(origin PLATFORM_STATE_DIR)),--state-dir "$(PLATFORM_STATE_DIR)",) $(if $(filter command line,$(origin PLATFORM_SECRET_DIR)),--secret-dir "$(PLATFORM_SECRET_DIR)",)
COMPOSE_FILES := --file compose.yaml --file compose.foundation.yaml --file compose.observability.yaml
COMPOSE_ENV_FILE ?= $(PLATFORM_VALUES_DIR)/compose.env
PIN_MANIFEST ?= artifacts.lock.json
PIN_PLAN ?= $(PLATFORM_VALUES_DIR)/plan.json
ACCEPT_PLAN ?= $(PLATFORM_VALUES_DIR)/plan.json
ACCEPT_MANIFEST ?= $(PIN_MANIFEST)
COMPOSE_CLEAR_ENV = env $(shell jq -r '.compose_keys[] | "-u " + .' "$(PIN_PLAN)")
COMPOSE_FULL = $(COMPOSE_CLEAR_ENV) $(DOCKER) compose --project-name $(PROJECT) $(COMPOSE_FILES) --env-file "$(COMPOSE_ENV_FILE)"
COMPOSE_BUILD = $(COMPOSE_FULL) --file compose.build.yaml
ENV_FILE_ARG = $(if $(PLATFORM_ENV_FILE),--env-file "$(PLATFORM_ENV_FILE)",)

.PHONY: config validate plan build-or-reuse up deploy-local status logs down restart upgrade rollback init-local backup restore
config:
	$(UV) run --locked python -m tools.environment --manifest "$(PIN_MANIFEST)" --output "$(PLATFORM_VALUES_DIR)" $(ENV_FILE_ARG) $(SETTINGS_CLI)
validate: config
	@case '$(PROJECT)' in poker-platform-*) ;; *) echo 'Choose an explicit poker-platform-* local project'; exit 1;; esac
	$(COMPOSE_BUILD) config --no-env-resolution --quiet
config-check: validate
plan: validate
	$(COMPOSE_FULL) config --no-env-resolution --services
	$(COMPOSE_FULL) config --no-env-resolution --images
init-local: local-only
	@install -d -m 700 "$(DEPLOY_SECRET_DIR)" "$(DEPLOY_STATE_DIR)/backups"
	@set -eu; umask 077; for name in auth accounts; do \
		if ! test -e "$(DEPLOY_SECRET_DIR)/$$name-db-password"; then openssl rand -hex 24 | tr -d '\n' > "$(DEPLOY_SECRET_DIR)/$$name-db-password"; fi; \
		if ! test -e "$(DEPLOY_SECRET_DIR)/$$name.env"; then printf 'DATABASE_URL=postgresql+asyncpg://app:%s@%s-db:5432/%s\n' "$$(cat "$(DEPLOY_SECRET_DIR)/$$name-db-password")" "$$name" "$$name" > "$(DEPLOY_SECRET_DIR)/$$name.env"; fi; \
	done; if ! test -e "$(DEPLOY_SECRET_DIR)/grafana-admin-password"; then openssl rand -hex 24 | tr -d '\n' > "$(DEPLOY_SECRET_DIR)/grafana-admin-password"; fi
local-only: config
	@jq -e '.settings.environment != "remote"' "$(PLATFORM_VALUES_DIR)/plan.json" >/dev/null || { echo "Remote environment is prepared-only"; exit 1; }
build-or-reuse: local-only validate
	@set -eu; $(COMPOSE_BUILD) config --no-env-resolution --format json | jq -r '.services[] | select(.build) | [.build.context,.build.args.SOURCE_COMMIT,(.build.args.SOURCE_DATE_EPOCH // 0)] | @tsv' | while IFS="$$(printf '\t')" read -r directory revision epoch; do \
		test "$$(git -C "$$directory" rev-parse HEAD)" = "$$revision" || { echo "Source pin mismatch: $$directory"; exit 1; }; \
		test "$$epoch" = 0 || test "$$(git -C "$$directory" log -1 --pretty=%ct)" = "$$epoch" || { echo "Source timestamp mismatch: $$directory"; exit 1; }; \
		test -z "$$(git -C "$$directory" status --porcelain)" || { echo "Source checkout must be clean: $$directory"; exit 1; }; \
	done
	@test -d "$(DEPLOY_STATE_DIR)/sdk-source/pypokerlost.git/objects" || { echo 'Prepare the documented private bare SDK cache first'; exit 1; }
	$(MAKE) init-local
	$(COMPOSE_BUILD) build --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg NO_PROXY
	@umask 077; $(COMPOSE_FULL) config --images | xargs $(DOCKER) image inspect --format '{{json .}}' > "$(DEPLOY_STATE_DIR)/images.jsonl"
images-ready:
	@$(COMPOSE_FULL) config --no-env-resolution --images | sort -u | xargs $(DOCKER) image inspect --format '{{.Id}}' >/dev/null
	@set -eu; jq -r '.images | to_entries[] | select(.value.sourceCommit) | [.key,.value.sourceCommit] | @tsv' "$(PIN_MANIFEST)" | while IFS="$$(printf '\t')" read -r name revision; do \
		ref=$$(jq -r --arg name "$$name" '.images[$$name]' "$(PIN_PLAN)"); \
		test "$$($(DOCKER) image inspect "$$ref" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')" = "$$revision" || { echo "Image source receipt mismatch: $$name"; exit 1; }; \
	done
up deploy-local: local-only validate images-ready
	$(MAKE) init-local
	$(COMPOSE_FULL) up --detach --no-build --wait --wait-timeout 180
	$(MAKE) accept-local
	@cp "$(PLATFORM_VALUES_DIR)/compose.env" "$(PLATFORM_VALUES_DIR)/active.env"
	@cp "$(PLATFORM_VALUES_DIR)/plan.json" "$(PLATFORM_VALUES_DIR)/active-plan.json"
	@cp "$(PIN_MANIFEST)" "$(PLATFORM_VALUES_DIR)/active-artifacts.json"
.PHONY: accept-local
accept-local:
	PLATFORM_TEST_URL="http://127.0.0.1:$$(jq -r .settings.http_port "$(ACCEPT_PLAN)")" PLATFORM_TEST_PLAN="$(ACCEPT_PLAN)" PLATFORM_TEST_MANIFEST="$(ACCEPT_MANIFEST)" $(UV) run --locked pytest tests/platform_integration.py tests/observability_integration.py --junitxml=coverage/local-profile.xml
status:
	$(COMPOSE_FULL) ps --all
logs:
	$(COMPOSE_FULL) logs --tail 100
restart: local-only images-ready
	$(COMPOSE_FULL) restart auth-db accounts-db prometheus loki alloy grafana
	$(COMPOSE_FULL) up --detach --no-build --wait --wait-timeout 180
	$(MAKE) accept-local
down:
	$(COMPOSE_FULL) down
upgrade: validate local-only images-ready
	@test -f "$(PLATFORM_VALUES_DIR)/active.env"
	@cp "$(PLATFORM_VALUES_DIR)/active.env" "$(PLATFORM_VALUES_DIR)/rollback.env"
	@cp "$(PLATFORM_VALUES_DIR)/active-plan.json" "$(PLATFORM_VALUES_DIR)/rollback-plan.json"
	@cp "$(PLATFORM_VALUES_DIR)/active-artifacts.json" "$(PLATFORM_VALUES_DIR)/rollback-artifacts.json"
	$(COMPOSE_FULL) up --detach --no-build --wait --wait-timeout 180
	$(MAKE) accept-local
	@cp "$(PLATFORM_VALUES_DIR)/compose.env" "$(PLATFORM_VALUES_DIR)/active.env"
	@cp "$(PLATFORM_VALUES_DIR)/plan.json" "$(PLATFORM_VALUES_DIR)/active-plan.json"
	@cp "$(PIN_MANIFEST)" "$(PLATFORM_VALUES_DIR)/active-artifacts.json"
rollback: local-only
	@test -f "$(PLATFORM_VALUES_DIR)/rollback.env"
	$(MAKE) images-ready COMPOSE_ENV_FILE="$(PLATFORM_VALUES_DIR)/rollback.env" PIN_MANIFEST="$(PLATFORM_VALUES_DIR)/rollback-artifacts.json" PIN_PLAN="$(PLATFORM_VALUES_DIR)/rollback-plan.json"
	env $$(jq -r '.compose_keys[] | "-u " + .' "$(PLATFORM_VALUES_DIR)/rollback-plan.json") $(DOCKER) compose --project-name $(PROJECT) $(COMPOSE_FILES) --env-file "$(PLATFORM_VALUES_DIR)/rollback.env" up --detach --no-build --wait --wait-timeout 180
	$(MAKE) accept-local ACCEPT_PLAN="$(PLATFORM_VALUES_DIR)/rollback-plan.json" ACCEPT_MANIFEST="$(PLATFORM_VALUES_DIR)/rollback-artifacts.json"
	@cp "$(PLATFORM_VALUES_DIR)/rollback.env" "$(PLATFORM_VALUES_DIR)/active.env"
	@cp "$(PLATFORM_VALUES_DIR)/rollback-plan.json" "$(PLATFORM_VALUES_DIR)/active-plan.json"
	@cp "$(PLATFORM_VALUES_DIR)/rollback-artifacts.json" "$(PLATFORM_VALUES_DIR)/active-artifacts.json"
BACKUP_DIR ?=
RESTORE_PROJECT ?=
RESTORE_STATE_DIR ?=
RESTORE_VALUES_DIR ?= $(CURDIR)/.local/restores/$(RESTORE_PROJECT)
RESTORE_PORT_OFFSET ?= 1000
RESTORE_COMPOSE = env $(shell jq -r '.compose_keys[] | "-u " + .' "$(RESTORE_VALUES_DIR)/plan.json") $(DOCKER) compose --project-name $(RESTORE_PROJECT) --file "$(BACKUP_DIR)/compose.yaml" --file "$(BACKUP_DIR)/compose.foundation.yaml" --file "$(BACKUP_DIR)/compose.observability.yaml" --env-file "$(RESTORE_VALUES_DIR)/compose.env"

backup: local-only images-ready
	@cmp -s "$(PLATFORM_VALUES_DIR)/compose.env" "$(PLATFORM_VALUES_DIR)/active.env" || { echo 'Select the accepted active environment before backup'; exit 1; }
	@cmp -s "$(PIN_MANIFEST)" "$(PLATFORM_VALUES_DIR)/active-artifacts.json" || { echo 'Artifact selection differs from the accepted active profile'; exit 1; }
	@set -eu; umask 077; \
		backup_dir="$(DEPLOY_STATE_DIR)/backups/$$(date -u +%Y%m%dT%H%M%SZ)-$(PROJECT)"; \
		mkdir "$$backup_dir"; mkdir "$$backup_dir/secrets"; \
		cp compose.yaml compose.foundation.yaml compose.observability.yaml "$$backup_dir/"; \
		cp "$(PIN_MANIFEST)" "$$backup_dir/artifacts.lock.json"; \
		manifest_dir=$$(dirname "$(PIN_MANIFEST)"); \
		cp -R "$$manifest_dir/observability" "$$backup_dir/observability"; \
		cp -R "$$manifest_dir/deploy" "$$backup_dir/deploy"; \
		cp -R "$$(jq -r .config_dir "$(PLATFORM_VALUES_DIR)/plan.json")" "$$backup_dir/rendered-config"; \
		cp "$(PLATFORM_VALUES_DIR)/compose.env" "$(PLATFORM_VALUES_DIR)/plan.json" "$$backup_dir/"; \
		$(COMPOSE_FULL) config --no-env-resolution --images | sort -u | while IFS= read -r ref; do printf '%s\t%s\n' "$$ref" "$$($(DOCKER) image inspect "$$ref" --format '{{.Id}}')"; done > "$$backup_dir/images.tsv"; \
		for name in auth-db-password accounts-db-password auth.env accounts.env grafana-admin-password; do cp "$(DEPLOY_SECRET_DIR)/$$name" "$$backup_dir/secrets/$$name"; done; \
		$(COMPOSE_FULL) stop gateway web auth accounts virtual-money poker crypto; \
		trap 'result=$$?; trap - EXIT; if ! $(COMPOSE_FULL) up --detach --no-build --wait --wait-timeout 180 >&2; then exit 1; fi; if ! $(MAKE) accept-local >&2; then exit 1; fi; exit "$$result"' EXIT; \
		for name in auth accounts; do $(COMPOSE_FULL) exec -T $$name-db pg_dump --username app --format custom --dbname $$name > "$$backup_dir/$$name.dump"; done; \
		$(COMPOSE_FULL) stop prometheus loki alloy grafana; \
		for pair in prometheus:/prometheus loki:/loki grafana:/var/lib/grafana; do \
			name=$${pair%%:*}; directory=$${pair#*:}; cid=$$($(COMPOSE_FULL) ps --all --quiet "$$name"); \
			$(DOCKER) cp "$$cid:$$directory/." - > "$$backup_dir/$$name.tar"; \
		done; \
		(cd "$$backup_dir" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS); \
		printf '%s\n' "$$backup_dir" > "$(DEPLOY_STATE_DIR)/latest-backup.txt"; \
		printf 'Private backup: %s\n' "$$backup_dir"

restore:
	@$(DOCKER) info >/dev/null
	@test -n "$(BACKUP_DIR)" -a -n "$(RESTORE_STATE_DIR)" || { echo 'Set BACKUP_DIR and a new external RESTORE_STATE_DIR'; exit 1; }
	@case '$(RESTORE_PROJECT)' in poker-platform-restore-*) ;; *) echo 'Choose a new poker-platform-restore-* destination'; exit 1;; esac
	@test '$(RESTORE_PROJECT)' != '$(PROJECT)'
	@test -z "$$($(DOCKER) ps --all --quiet --filter label=com.docker.compose.project=$(RESTORE_PROJECT))" || { echo 'Destination containers already exist'; exit 1; }
	@test -z "$$($(DOCKER) volume ls --quiet --filter label=com.docker.compose.project=$(RESTORE_PROJECT))" || { echo 'Destination volumes already exist'; exit 1; }
	@test ! -e "$(RESTORE_STATE_DIR)" || { echo 'Destination state already exists'; exit 1; }
	@cd "$(BACKUP_DIR)" && sha256sum --check --quiet SHA256SUMS
	@set -eu; while IFS="$$(printf '\t')" read -r ref expected; do test "$$($(DOCKER) image inspect "$$ref" --format '{{.Id}}')" = "$$expected" || { echo "Backup image identity changed: $$ref"; exit 1; }; done < "$(BACKUP_DIR)/images.tsv"
	@set -eu; \
		export PLATFORM_HTTP_PORT=$$(($$(jq -r .settings.http_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		export PLATFORM_HTTPS_PORT=$$(($$(jq -r .settings.https_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		export PLATFORM_PROMETHEUS_PORT=$$(($$(jq -r .settings.prometheus_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		export PLATFORM_GRAFANA_PORT=$$(($$(jq -r .settings.grafana_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		export PLATFORM_LOKI_PORT=$$(($$(jq -r .settings.loki_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		export PLATFORM_ALLOY_PORT=$$(($$(jq -r .settings.alloy_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		export PLATFORM_SYSLOG_PORT=$$(($$(jq -r .settings.syslog_port "$(BACKUP_DIR)/plan.json") + $(RESTORE_PORT_OFFSET))); \
		$(UV) run --locked python -m tools.environment --manifest "$(BACKUP_DIR)/artifacts.lock.json" --env-file "$(BACKUP_DIR)/compose.env" --state-dir "$(RESTORE_STATE_DIR)" --secret-dir "$(RESTORE_STATE_DIR)/secrets" --output "$(RESTORE_VALUES_DIR)"
	@$(RESTORE_COMPOSE) config --no-env-resolution --quiet
	@$(RESTORE_COMPOSE) config --no-env-resolution --images | sort -u | xargs $(DOCKER) image inspect --format '{{.Id}}' >/dev/null
	@set -eu; umask 077; install -d -m 700 "$(RESTORE_STATE_DIR)/secrets"; for name in auth-db-password accounts-db-password auth.env accounts.env grafana-admin-password; do cp "$(BACKUP_DIR)/secrets/$$name" "$(RESTORE_STATE_DIR)/secrets/$$name"; done
	$(RESTORE_COMPOSE) create --no-build prometheus loki alloy grafana
	@set -eu; for pair in prometheus:/prometheus loki:/loki grafana:/var/lib/grafana; do \
		name=$${pair%%:*}; directory=$${pair#*:}; cid=$$($(RESTORE_COMPOSE) ps --all --quiet "$$name"); \
		$(DOCKER) cp --archive - "$$cid:$$directory" < "$(BACKUP_DIR)/$$name.tar"; \
	done
	$(RESTORE_COMPOSE) up --detach --no-build --wait --wait-timeout 180 auth-db accounts-db
	@set -eu; for name in auth accounts; do $(RESTORE_COMPOSE) exec -T $$name-db pg_restore --username app --dbname $$name --exit-on-error < "$(BACKUP_DIR)/$$name.dump"; done
	$(RESTORE_COMPOSE) up --detach --no-build --wait --wait-timeout 180
	$(MAKE) accept-local ACCEPT_PLAN="$(RESTORE_VALUES_DIR)/plan.json" ACCEPT_MANIFEST="$(BACKUP_DIR)/artifacts.lock.json"
	@cp "$(RESTORE_VALUES_DIR)/compose.env" "$(RESTORE_VALUES_DIR)/active.env"
	@cp "$(RESTORE_VALUES_DIR)/plan.json" "$(RESTORE_VALUES_DIR)/active-plan.json"
	@cp "$(BACKUP_DIR)/artifacts.lock.json" "$(RESTORE_VALUES_DIR)/active-artifacts.json"
	@echo 'Restored into the new disposable project; original volumes and state remain intact.'

# Private ready application artifacts; official dependencies retain manifest digests.
IMAGE_BUNDLE_DIR ?=
.PHONY: export-images load-images
export-images: local-only images-ready
	@test -n "$(IMAGE_BUNDLE_DIR)" -a ! -e "$(IMAGE_BUNDLE_DIR)" || { echo 'Choose a new private IMAGE_BUNDLE_DIR outside checkouts'; exit 1; }
	@set -eu; umask 077; install -d -m 700 "$(IMAGE_BUNDLE_DIR)"; \
		cp "$(PIN_MANIFEST)" "$(IMAGE_BUNDLE_DIR)/artifacts.lock.json"; \
		manifest_dir=$$(dirname "$(PIN_MANIFEST)"); \
		cp -R "$$manifest_dir/deploy" "$(IMAGE_BUNDLE_DIR)/deploy"; \
		cp -R "$$manifest_dir/observability" "$(IMAGE_BUNDLE_DIR)/observability"; \
		jq -r '.images | to_entries[] | select(.value.sourceCommit) | .key' "$(PIN_MANIFEST)" | while IFS= read -r name; do jq -r --arg name "$$name" '.images[$$name]' "$(PIN_PLAN)"; done > "$(IMAGE_BUNDLE_DIR)/refs.txt"; \
		while IFS= read -r ref; do printf '%s\t%s\n' "$$ref" "$$($(DOCKER) image inspect "$$ref" --format '{{.Id}}')"; done < "$(IMAGE_BUNDLE_DIR)/refs.txt" > "$(IMAGE_BUNDLE_DIR)/image-receipts.tsv"; \
		xargs $(DOCKER) image save < "$(IMAGE_BUNDLE_DIR)/refs.txt" | gzip --no-name > "$(IMAGE_BUNDLE_DIR)/app-images.tar.gz"; \
		(cd "$(IMAGE_BUNDLE_DIR)" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
load-images: local-only
	@test -n "$(IMAGE_BUNDLE_DIR)"
	@cmp -s "$(PIN_MANIFEST)" "$(IMAGE_BUNDLE_DIR)/artifacts.lock.json" || { echo 'Select the bundle manifest with PIN_MANIFEST'; exit 1; }
	@cd "$(IMAGE_BUNDLE_DIR)" && sha256sum --check --quiet SHA256SUMS
	$(DOCKER) image load --input "$(IMAGE_BUNDLE_DIR)/app-images.tar.gz"
	@set -eu; while IFS="$$(printf '\t')" read -r ref expected; do test "$$($(DOCKER) image inspect "$$ref" --format '{{.Id}}')" = "$$expected" || { echo "Loaded image identity mismatch: $$ref"; exit 1; }; done < "$(IMAGE_BUNDLE_DIR)/image-receipts.tsv"
	$(MAKE) images-ready
