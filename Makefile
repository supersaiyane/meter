# Meter. One entry point for every routine task.
# Run `make` or `make help` for the list.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Matches the runtime image, reg.mini.dev/python:3.13. A venv on a newer
# interpreter passes tests locally that can fail in the container, and the
# difference is invisible until CI. Verified present on this machine at
# TASK-P0-029.
PY            ?= python3.13
VENV          ?= .venv
BIN           := $(VENV)/bin
COMPOSE       ?= docker compose
TF            ?= terraform
TF_ENV        ?= dev
IMAGE_TAG     ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo local)
AWS_REGION    ?= eu-west-1
ECR_REGISTRY  ?= $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

# The target servers are amd64. A build on Apple Silicon produces arm64 by
# default and `docker push` does not convert it, so the amd64 host fails at
# runtime with "exec format error". Every build path below pins the platform.
# Override only if you genuinely need a different target.
PLATFORM      ?= linux/amd64

PY_SRC := finops_core finops_providers finops_ingest finops_api finops_mcp tests

# The documentation and policy scripts need pyyaml, which a system interpreter
# will not have and PEP 668 will not let us add. So they run from the venv when
# it exists. Before `make setup`, they fall back and fail with a clear message
# rather than a ModuleNotFoundError.
DOCPY := $(shell test -x $(BIN)/python && echo $(BIN)/python || echo $(PY))

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_.-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

.PHONY: setup
setup: security-tools ## Create the virtualenv and install everything, including the scanners
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip setuptools wheel
	$(BIN)/pip install -e ".[dev]"
	cd finops-web && npm ci
	@echo
	@echo "Setup complete. Activate with: source $(BIN)/activate"
	@echo "Next: make hooks-install, then make up"

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
check-docs: ## Fail if any generated document is out of step with the registry
	@$(DOCPY) scripts/docs/sync.py --check
	@$(DOCPY) scripts/docs/check_index.py
	@$(DOCPY) scripts/docs/check_feature_docs.py
	@$(DOCPY) scripts/docs/build_file_graph.py --check
	@$(DOCPY) scripts/docs/build_context_index.py --check
	@$(DOCPY) scripts/ci/check_flags.py
	@$(DOCPY) scripts/ci/check_hardcoded.py
	@$(DOCPY) scripts/ci/check_forbidden_imports.py

.PHONY: doc-sync
doc-sync: ## Regenerate every derived document from docs/registry.yaml and the source
	@$(DOCPY) scripts/docs/sync.py
	@$(DOCPY) scripts/docs/build_file_graph.py
	@$(DOCPY) scripts/docs/build_context_index.py
	@echo "Derived documents regenerated. Review the diff before committing."

.PHONY: session-end
session-end: doc-sync ## Run at the end of every work session
	@$(DOCPY) scripts/docs/check_index.py
	@$(DOCPY) scripts/docs/check_feature_docs.py
	@$(MAKE) check-writing
	@echo
	@echo "Remaining, by hand:"
	@echo "  1. Add a row to docs/checkpoint.md with a resume vector"
	@echo "  2. Update tasks/STATUS.md if a task changed state"
	@echo "  3. Add a lesson to tasks/lessons.md if you were corrected"
	@echo "  4. Commit. The generated files are already updated." 

.PHONY: graph
graph: ## Rebuild the file dependency graph and check the layering
	@$(DOCPY) scripts/docs/build_file_graph.py
	@echo "docs/architecture/file-graph.md and file-graph.json"

.PHONY: review
review: ## Automated code review of the working tree. See ADR-0011
	@$(DOCPY) scripts/ci/code_review.py --output security/reviews

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

# ---------------------------------------------------------------- agent session

# pxpipe is a local proxy that logs and compresses Claude Code traffic. It has
# to wrap the launch, so a session started with plain `claude` is not logged and
# cannot be attached to afterwards.
#
# Meter exists to meter things. Not measuring the cost of building it would be
# a poor look.

PXPIPE_LOG ?= $(HOME)/.pxpipe/events.jsonl

.PHONY: dev
dev: ## Start a Claude Code session behind pxpipe, so token usage is recorded
	@command -v pxpipe >/dev/null 2>&1 || { \
	  echo "pxpipe not found. brew install pxpipe, or see https://github.com/"; \
	  exit 2; \
	}
	@echo "Launching Claude Code behind pxpipe. Usage lands in $(PXPIPE_LOG)."
	@echo "Run 'make stats' afterwards, or during, from another shell."
	pxpipe warp -- claude

.PHONY: stats
stats: ## Report token usage and measured savings from the pxpipe log
	@command -v pxpipe >/dev/null 2>&1 || { echo "pxpipe not found"; exit 2; }
	@test -s "$(PXPIPE_LOG)" || { \
	  echo "No pxpipe log at $(PXPIPE_LOG)."; \
	  echo "A session started with plain 'claude' is not recorded. Use 'make dev'."; \
	  exit 1; \
	}
	@echo "Log: $(PXPIPE_LOG)  (last written: $$(date -r "$(PXPIPE_LOG)" '+%Y-%m-%d %H:%M'))"
	@echo
	@pxpipe stats

.PHONY: stats-json
stats-json: ## The same numbers as JSON, for anything that wants to consume them
	@pxpipe stats --json

# ---------------------------------------------------------------- local stack

.PHONY: up
up: local-auth.yaml .env ## Start the full local stack, then run migrations
	$(COMPOSE) up -d --build
	$(MAKE) migrate
	@echo "API  http://localhost:8000/docs"
	@echo "Web  http://localhost:5173"

# Docker creates a directory when a bind mount source is missing, so without
# this the API starts with a directory where its config should be and fails
# confusingly. The first command a new engineer runs used to be the one that
# broke. AUDIT-001, finding A001-F04.
.env:
	@cp .env.example .env
	@echo "Created .env from the example. It is gitignored."
	@echo "Every value is documented there with what it does and which file reads it."

local-auth.yaml:
	@cp local-auth.example.yaml local-auth.yaml
	@echo "Created local-auth.yaml from the example. It is gitignored."

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

# ---------------------------------------------------------------- security

.PHONY: security-scan
security-scan: ## Full scan: deps, secrets, terraform. Writes a timestamped report
	@bash scripts/security/scan.sh

.PHONY: security-scan-images
security-scan-images: build ## Scan the built images as well
	@bash scripts/security/scan.sh --images

.PHONY: scan-local
scan-local: build ## Scan the locally built images using the compose security profile
	IMAGE_TAG=$(IMAGE_TAG) $(COMPOSE) --profile security run --rm sbom
	IMAGE_TAG=$(IMAGE_TAG) $(COMPOSE) --profile security run --rm grype  || true
	IMAGE_TAG=$(IMAGE_TAG) $(COMPOSE) --profile security run --rm trivy  || true
	@$(MAKE) security-report

.PHONY: hooks-install
hooks-install: ## Install the pre commit and pre push gates
	$(BIN)/pip install pre-commit
	$(BIN)/pre-commit install
	$(BIN)/pre-commit install --hook-type pre-push
	@echo "Installed. Pre commit: writing rules, secrets, lint, doc sync."
	@echo "Pre push: full security scan and tests."

.PHONY: verify-provenance
verify-provenance: ## Verify an image signature and SBOM attestation before deploy
	@test -n "$(AWS_ACCOUNT_ID)" || (echo "AWS_ACCOUNT_ID is required"; exit 1)
	@for svc in api worker web; do \
	  cosign verify $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG) \
	    --certificate-identity-regexp "$(COSIGN_IDENTITY_REGEXP)" \
	    --certificate-oidc-issuer "$(COSIGN_OIDC_ISSUER)"; \
	  cosign verify-attestation --type spdxjson \
	    $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG) \
	    --certificate-identity-regexp "$(COSIGN_IDENTITY_REGEXP)" \
	    --certificate-oidc-issuer "$(COSIGN_OIDC_ISSUER)" > /dev/null; \
	  echo "OK: meter-$$svc signed and attested"; \
	done

.PHONY: security-scan-deployed
security-scan-deployed: ## Scan a running digest. What the nightly job uses
	@test -n "$(DIGEST)" || (echo 'Usage: make security-scan-deployed DIGEST=sha256:...'; exit 1)
	@bash scripts/security/scan.sh --digest "$(DIGEST)"

.PHONY: security-report
security-report: ## Rebuild the HTML report from the latest scan
	@$(DOCPY) scripts/security/report.py \
	  --input security/reports/latest \
	  --allowlist security/policy/allowlist.yaml \
	  --output security/reports/latest/index.html \
	  --summary security/reports/latest/summary.json \
	  --posture security/POSTURE.md
	@echo "security/reports/latest/index.html"

.PHONY: security-fix
security-fix: ## Apply available fixes on a branch, run tests, re scan. Never merges
	@$(DOCPY) scripts/security/autofix.py --summary security/reports/latest/summary.json --apply

.PHONY: security-fix-dry
security-fix-dry: ## Show what security-fix would change
	@$(DOCPY) scripts/security/autofix.py --summary security/reports/latest/summary.json

.PHONY: dep-check
dep-check: ## Admission gate before adding a dependency. Usage: make dep-check pkg=name
	@test -n "$(pkg)" || (echo 'Usage: make dep-check pkg=<package>  [npm=1]'; exit 1)
	@if [ -n "$(npm)" ]; then \
	  bash scripts/security/check_dependency.sh --npm "$(pkg)"; \
	else \
	  bash scripts/security/check_dependency.sh "$(pkg)"; \
	fi

.PHONY: sbom
sbom: ## Generate an SBOM for each image
	@for svc in api worker web; do \
	  syft "meter-$$svc:$(IMAGE_TAG)" -o spdx-json \
	    > "security/sbom/$$svc-$(IMAGE_TAG).spdx.json"; \
	  echo "security/sbom/$$svc-$(IMAGE_TAG).spdx.json"; \
	done

.PHONY: security-tools
base-images: ## Re resolve the Minimus base image digests and rewrite the lock
	@$(DOCPY) scripts/ci/refresh_base_images.py

.PHONY: base-images-check
base-images-check: ## Fail if a pinned base image digest has drifted upstream
	@$(DOCPY) scripts/ci/refresh_base_images.py --check

.PHONY: security-tools
security-tools: ## Install the scanners. Runs as part of make setup
	@echo "Installing grype, syft, trivy, gitleaks, cosign"
	@if command -v brew >/dev/null 2>&1; then \
	  brew list grype   >/dev/null 2>&1 || brew install grype; \
	  brew list syft    >/dev/null 2>&1 || brew install syft; \
	  brew list trivy   >/dev/null 2>&1 || brew install trivy; \
	  brew list gitleaks >/dev/null 2>&1 || brew install gitleaks; \
	  brew list cosign  >/dev/null 2>&1 || brew install cosign; \
	else \
	  echo "Homebrew not found. Install manually, see security/README.md"; \
	fi
	@test -x $(BIN)/pip && $(BIN)/pip install --quiet pip-audit || true

# ---------------------------------------------------------------- images

.PHONY: build
build: ## Build all three images for $(PLATFORM), tagged with the short commit
	docker buildx build --platform $(PLATFORM) --load \
	  --build-arg GIT_SHA=$(IMAGE_TAG) \
	  -f docker/Dockerfile.api    -t meter-api:$(IMAGE_TAG)    .
	docker buildx build --platform $(PLATFORM) --load \
	  --build-arg GIT_SHA=$(IMAGE_TAG) \
	  -f docker/Dockerfile.worker -t meter-worker:$(IMAGE_TAG) .
	docker buildx build --platform $(PLATFORM) --load \
	  --build-arg GIT_SHA=$(IMAGE_TAG) \
	  -f docker/Dockerfile.web    -t meter-web:$(IMAGE_TAG)    .
	@$(MAKE) verify-platform

.PHONY: verify-platform
verify-platform: ## Fail if a built image is not $(PLATFORM). Catches the arm64 mistake
	@expected="$(PLATFORM)"; \
	for svc in api worker web; do \
	  actual=$$(docker image inspect meter-$$svc:$(IMAGE_TAG) \
	    --format '{{.Os}}/{{.Architecture}}' 2>/dev/null || echo "missing"); \
	  if [ "$$actual" != "$$expected" ]; then \
	    echo "FAIL: meter-$$svc is $$actual, expected $$expected."; \
	    echo "      A push will not convert it. Rebuild with 'make build'."; \
	    exit 1; \
	  fi; \
	  echo "OK: meter-$$svc is $$actual"; \
	done

.PHONY: buildx-setup
buildx-setup: ## Create the buildx builder needed for cross platform builds
	docker buildx create --name meter --use --bootstrap 2>/dev/null || docker buildx use meter
	docker buildx inspect --bootstrap

.PHONY: ecr-login
ecr-login: ## Authenticate Docker against ECR
	aws ecr get-login-password --region $(AWS_REGION) \
	  | docker login --username AWS --password-stdin $(ECR_REGISTRY)

.PHONY: push
push: ecr-login verify-platform ## Push all three images to ECR. Normally done by GitLab CI
	@test -n "$(AWS_ACCOUNT_ID)" || (echo "AWS_ACCOUNT_ID is required"; exit 1)
	for svc in api worker web; do \
	  docker tag meter-$$svc:$(IMAGE_TAG) $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG); \
	  docker push $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG); \
	done
	@$(MAKE) verify-pushed-platform

.PHONY: verify-pushed-platform
verify-pushed-platform: ## Confirm the registry manifest reports $(PLATFORM)
	@for svc in api worker web; do \
	  echo "$$svc: $$(docker buildx imagetools inspect \
	    $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG) --format '{{json .Manifest}}' \
	    2>/dev/null | head -c 200)"; \
	done

.PHONY: buildx-push
buildx-push: ecr-login ## Build for $(PLATFORM) and push in one step, no local load
	@test -n "$(AWS_ACCOUNT_ID)" || (echo "AWS_ACCOUNT_ID is required"; exit 1)
	for svc in api worker web; do \
	  docker buildx build --platform $(PLATFORM) --push \
	    --build-arg GIT_SHA=$(IMAGE_TAG) \
	    --provenance=true --sbom=true \
	    -f docker/Dockerfile.$$svc \
	    -t $(ECR_REGISTRY)/meter-$$svc:$(IMAGE_TAG) .; \
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
verify: lint check-writing check-docs test security-scan ## Everything CI runs on a merge request
	@echo "verify passed"

.PHONY: ci
ci: verify test-integration ## Everything CI runs on the default branch
	@echo "ci passed"
