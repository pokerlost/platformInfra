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
VALUES_DIR := .local/generated
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
	$(UV) run --locked pytest --cov --cov-report=term-missing --cov-report=json --cov-report=xml
test: test-unit
test-integration:
	$(UV) run --locked pytest tests/platform_integration.py --junitxml=coverage/platform.xml
test-database:
	$(UV) run --locked pytest tests/postgres_integration.py --junitxml=coverage/postgres.xml
check: lint typecheck test-unit
values:
	$(UV) run --locked python -m tools.artifacts --output $(VALUES_DIR) --release $(RELEASE) --namespace $(NAMESPACE)
preview-values:
	$(UV) run --locked python -m tools.artifacts --output $(VALUES_DIR) --preview --release $(RELEASE) --namespace $(NAMESPACE)
up: values
	$(MAKE) init-local
	$(COMPOSE) --file compose.foundation.yaml up --detach --wait --wait-timeout 180
preview: preview-values
	$(COMPOSE) up --detach --wait --wait-timeout 60
down: preview-values
	$(COMPOSE) down --remove-orphans
status: preview-values
	$(COMPOSE) ps --all
logs: preview-values
	$(COMPOSE) logs --tail 100
init-local:
	@install -d -m 700 .local
	@set -e; umask 077; for name in auth accounts; do \
		if ! test -e .local/$$name-db-password; then databasePassword=$$(openssl rand -hex 24); printf '%s' "$$databasePassword" > .local/$$name-db-password; fi; \
		if ! test -e .local/$$name.env; then \
			printf 'DATABASE_URL=postgresql+asyncpg://app:%s@%s-db:5432/%s\n' "$$(cat .local/$$name-db-password)" "$$name" "$$name" > .local/$$name.env; \
		fi; \
	done
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
	$(UV) run --locked python -c "from tools.artifacts import load_manifest; from pathlib import Path; load_manifest(Path('artifacts.lock.json'))"
	$(KUBE_LOCAL) apply -f deploy/crds/gateway-api-v1.6.3.yaml
	$(KUBE_LOCAL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBE_LOCAL) apply -f -
deploy-preview: preview-values gateway-api
	$(HELM_LOCAL) upgrade --install $(RELEASE)-web $(VALUES_DIR)/charts/web.tgz --values $(VALUES_DIR)/web.values.json $(HELM_FLAGS)
	$(HELM_LOCAL) upgrade --install $(RELEASE)-gateway $(VALUES_DIR)/charts/gateway.tgz --values $(VALUES_DIR)/gateway.values.json $(HELM_FLAGS)
deploy-local: values gateway-api
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
	@set -e; umask 077; for name in auth accounts; do \
		sed "s/@$$name-db:5432/@$(RELEASE)-$$name-db:5432/" .local/$$name.env > .local/$$name.k8s.env; \
		printf '%s' "$$(sed 's/^DATABASE_URL=//' .local/$$name.k8s.env)" > .local/$$name-database-url; \
		$(KUBE_LOCAL) create secret generic $(RELEASE)-$$name-database --namespace $(NAMESPACE) --from-file=DATABASE_URL=.local/$$name-database-url --from-file=POSTGRES_PASSWORD=.local/$$name-db-password --dry-run=client -o yaml | $(KUBE_LOCAL) apply -f -; \
	done
undeploy-local: local-context
	$(HELM_LOCAL) uninstall $(RELEASE)-gateway $(RELEASE)-web $(RELEASE)-auth $(RELEASE)-accounts $(RELEASE)-virtual-money $(RELEASE)-poker $(RELEASE)-crypto $(RELEASE)-databases --namespace $(NAMESPACE) --ignore-not-found --wait
	@echo "Database PVCs and existing Secrets are retained."
