# Meter. One entry point for every routine task.
# Run `make` or `make help` for the list.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PY            ?= python3
VENV          ?= .venv
BIN           := $(VENV)/bin
COMPOSE       ?= docker compose
TF            ?= terraform
TF_ENV        ?= dev
IMAGE_TAG     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo local)
AWS_REGION    ?= eu-west-1
ECR_REGISTRY  ?= $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

PY_SRC := finops_core finops_providers finops_ingest finops_api tests

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

.PHONY: setup
setup: ## Create the virtualenv and install everything, backend and frontend
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip setuptools wheel
	$(BIN)/pip install -e ".[dev]"
	cd finops-web && npm ci
	@echo "Setup complete. Activate with: source $(BIN)/activate"

.PHONY: clean
clean: ## Remove build artefacts and caches. Does not touch the database volume
	find . -type d -name __pycache__ -prune -exec $(RM) -r {} +
	find . -type d -name '*.egg-info' -prune -exec $(RM) -r {} +
	$(RM) -r .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage finops-web/dist

# ---------------------------------------------------------------- quality

.PHONY: fmt
fmt: ## Format Python and TypeScript in place
	$(BIN)/ruff format $(PY_SRC)
	$(BIN)/ruff check --fix $(PY_SRC)
	cd finops-web && npm run format

.PHONY: lint
lint: ## Lint everything, no changes written
	$(BIN)/ruff format --check $(PY_SRC)
	$(BIN)/ruff check $(PY_SRC)
	$(BIN)/mypy finops_core finops_providers finops_ingest finops_api
	$(BIN)/lint-imports
	cd finops-web && npm run lint
	$(TF) -chdir=infra/terraform/hub fmt -check -recursive

.PHONY: check-writing
check-writing: ## Fail if an em dash or en dash appears anywhere. See CLAUDE.md
	@if grep -rn $$'—\|–' \
	    --include='*.md' --include='*.py' --include='*.ts' --include='*.tsx' \
	    --include='*.tf' --include='*.yml' --include='*.yaml' \
	    --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.venv . ; then \
	  echo "FAIL: em dash or en dash found. See CLAUDE.md writing rules."; exit 1; \
	else \
	  echo "OK: no em dash or en dash"; \
	fi

.PHONY: check-docs
check-docs: ## Fail if INDEX.md is stale against the documents it indexes
	@$(PY) scripts/check_index.py

# ---------------------------------------------------------------- tests

.PHONY: test
test: ## Unit and contract tests, no external services needed
	$(BIN)/pytest -m "not integration"

.PHONY: test-integration
test-integration: ## Integration tests. Needs Docker for testcontainers
	$(BIN)/pytest -m integration

.PHONY: test-all
test-all: test test-integration ## Every backend test, plus frontend unit tests
	cd finops-web && npm run test -- --run

.PHONY: test-e2e
test-e2e: ## Playwright journeys against the local stack
	cd finops-web && npx playwright test

.PHONY: coverage
coverage: ## Test with an HTML coverage report at htmlcov/index.html
	$(BIN)/pytest --cov-report=html
	@echo "Report: htmlcov/index.html"

# ---------------------------------------------------------------- local stack

.PHONY: up
up: ## Start the full local stack, then run migrations
	$(COMPOSE) up -d --build
	$(MAKE) migrate
	@echo "API  http://localhost:8000/docs"
	@echo "Web  http://localhost:5173"

.PHONY: down
down: ## Stop the local stack, keep the database volume
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop the local stack and delete the database volume. Destroys local data
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Follow logs for every local service
	$(COMPOSE) logs -f

.PHONY: psql
psql: ## Open a psql shell against the local database
	$(COMPOSE) exec postgres psql -U meter -d meter

# ---------------------------------------------------------------- database

.PHONY: migrate
migrate: ## Apply migrations to the local database
	$(COMPOSE) run --rm api alembic upgrade head

.PHONY: migration
migration: ## Autogenerate a migration. Usage: make migration m="add org_node"
	@test -n "$(m)" || (echo 'Usage: make migration m="description"'; exit 1)
	$(COMPOSE) run --rm api alembic revision --autogenerate -m "$(m)"

# ---------------------------------------------------------------- images

.PHONY: build
build: ## Build all three images locally, tagged with the short commit
	docker build -f docker/Dockerfile.api    -t meter-api:$(IMAGE_TAG)    .
	docker build -f docker/Dockerfile.worker -t meter-worker:$(IMAGE_TAG) .
	docker build -f docker/Dockerfile.web    -t meter-web:$(IMAGE_TAG)    .

.PHONY: ecr-login
ecr-login: ## Authenticate Docker against ECR
	aws ecr get-login-password --region $(AWS_REGION) \
	  | docker login --username AWS --password-stdin $(ECR_REGISTRY)

.PHONY: push
push: ecr-login ## Push all three images to ECR. Normally done by GitLab CI
	@test -n "$(AWS_ACCOUNT_ID)" || (echo "AWS_ACCOUNT_ID is required"; exit 1)
	for svc in api worker web; do \
	  docker tag meter-$$svc:$(IMAGE_TAG) $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG); \
	  docker push $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG); \
	done

# ---------------------------------------------------------------- terraform

.PHONY: tf-init
tf-init: ## Initialise the hub stack for TF_ENV, default dev
	$(TF) -chdir=infra/terraform/hub init -backend-config=envs/$(TF_ENV).backend.hcl

.PHONY: tf-plan
tf-plan: ## Plan the hub stack for TF_ENV at the current image tag
	$(TF) -chdir=infra/terraform/hub plan \
	  -var-file=envs/$(TF_ENV).tfvars -var="image_tag=$(IMAGE_TAG)"

.PHONY: tf-apply
tf-apply: ## Apply the hub stack. CI does this on the default branch
	$(TF) -chdir=infra/terraform/hub apply \
	  -var-file=envs/$(TF_ENV).tfvars -var="image_tag=$(IMAGE_TAG)" -auto-approve

.PHONY: tf-member
tf-member: ## Apply the member account StackSet. Needs management account credentials
	$(TF) -chdir=infra/terraform/member apply -var-file=envs/$(TF_ENV).tfvars

# ---------------------------------------------------------------- gates

.PHONY: verify
verify: lint check-writing test ## Everything CI runs on a merge request
	@echo "verify passed"

.PHONY: ci
ci: verify test-integration ## Everything CI runs on the default branch
	@echo "ci passed"
