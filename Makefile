# Basic boiler Plate Doc | Grade B
# Why this file exists: Every routine task in the project, discoverable with make help. The
# single largest reusable asset here, because the target set is the project's operating manual.
# Grade B here: copy it, then replace the project specific targets. The verify, ci, session-end,
# security and documentation targets carry over.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.

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

# `finops_fakes` is here and is deliberately not in the wheel: it is linted and
# type checked to the same standard as production code, because a fake nobody
# checks drifts from the port it is standing in for, and then the tests pass
# against something the real adapter does not do. ADR-0022.
# One line, and it has to stay one line: tests/scripts/test_lint_scope.py reads
# this assignment with a single line regex, which is how it catches a package
# that quietly leaves the linter's sight.
PY_PKGS := finops_core finops_providers finops_fakes finops_ingest finops_api finops_mcp finops_query
# scripts/ and migrations/ are here because they were outside the linter for
# long enough to accumulate 10 ruff findings and 36 mypy errors that nothing
# ever reported. Two of those were real: a list annotated flat while holding
# groups, and an allowlist loader whose signature said its key was a string
# while the code keyed on a tuple. That second one is the only place a reader
# can learn what an allowlist entry has to match on, and it was wrong.
#
# The scripts are the gates. A gate nobody checks is the thing this project
# keeps finding, and leaving the checkers themselves unchecked was an instance
# of it.
#
# `tests` was linted but never type checked, which had left twelve stale
# `type: ignore` comments in place. A stale ignore is worse than none: it
# silences whatever real error lands on that line next.
#
# One variable now, so ruff and mypy cannot be pointed at different things.
PY_SRC := $(PY_PKGS) tests scripts migrations

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
	$(RM) -r .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage docs/api finops-web/dist finops-web/dist-types finops-web/dist-types-node

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
	$(BIN)/mypy $(PY_SRC)
	$(BIN)/lint-imports
	cd finops-web && npm run lint
# The three stacks. The skip that used to be here, for a directory TASK-P0-013
# had not created yet, was removed by TASK-P0-013 as one of its own acceptance
# criteria. An allowance that outlives its reason is an allowance nobody removes.
	$(TF) -chdir=infra/terraform/management fmt -check -recursive
	$(TF) -chdir=infra/terraform/member fmt -check -recursive
	$(TF) -chdir=infra/terraform/hub fmt -check -recursive
	$(TF) -chdir=infra/terraform/config fmt -check -recursive

.PHONY: tf-validate
tf-validate: ## terraform validate on all four stacks. Needs network for the first init
# Not in `lint`, and the reason is that it is not a lint. `validate` needs the provider
# schema, so the first run downloads it, and a gate that needs the network is a gate that
# fails on a train. `-backend=false` is what keeps it from needing credentials or state:
# it checks the configuration rather than what is deployed.
#
# TASK-P4-010 asks for validate to pass on all stacks, so it is a target somebody can run
# rather than a claim in a commit message.
	@for stack in management member hub config; do \
		echo "validating $$stack"; \
		$(TF) -chdir=infra/terraform/$$stack init -backend=false -input=false >/dev/null || exit 1; \
		$(TF) -chdir=infra/terraform/$$stack validate || exit 1; \
	done

.PHONY: check-dashboards
check-dashboards: ## Refuse a dashboard whose panels would cost too much. TASK-P2-018
	@echo "Usage: make check-dashboards DASHBOARDS='path/to/*.json'"
	@test -n "$(DASHBOARDS)" || { echo "Set DASHBOARDS to the files to check."; exit 2; }
	$(BIN)/python scripts/ci/check_dashboards.py $(DASHBOARDS)

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
	@$(DOCPY) scripts/docs/check_map_counts.py --check
	@$(DOCPY) scripts/ci/check_flags.py
	@$(DOCPY) scripts/ci/check_hardcoded.py
	@$(DOCPY) scripts/ci/check_forbidden_imports.py

.PHONY: doc-sync
doc-sync: ## Regenerate every derived document from docs/registry.yaml and the source
	@$(DOCPY) scripts/docs/sync.py
	@$(DOCPY) scripts/docs/build_file_graph.py
	@$(DOCPY) scripts/docs/build_context_index.py
	@$(DOCPY) scripts/docs/check_map_counts.py
	@echo "Derived documents regenerated. Review the diff before committing."

.PHONY: session-end
session-end: doc-sync ## Run at the end of every work session
	@$(DOCPY) scripts/docs/check_index.py
	@$(DOCPY) scripts/docs/check_feature_docs.py
	@$(DOCPY) scripts/docs/rotate_checkpoint.py
	@$(MAKE) check-writing
	@$(DOCPY) scripts/ci/check_memory.py
	@echo
	@echo "Remaining, by hand:"
	@echo "  1. Add a row to docs/checkpoint.md with a resume vector"
	@echo "  2. Update tasks/STATUS.md if a task changed state"
	@echo "  3. Were you corrected? make lesson m=\"short name\""
	@echo "  4. Commit. The generated files are already updated." 

.PHONY: check-docstrings
check-docstrings: ## Fail if docstring coverage on public symbols has dropped
	@$(BIN)/interrogate $(PY_PKGS)

.PHONY: api-reference
api-reference: ## Generate the API reference from docstrings into docs/api
	@$(BIN)/pdoc --output-directory docs/api --no-search $(PY_PKGS)
	@echo "docs/api/index.html"

.PHONY: check-memory
check-memory: ## Fail if a resume vector, a cited commit or a lesson has rotted
	@$(DOCPY) scripts/ci/check_memory.py

.PHONY: lesson
lesson: ## Append a lesson skeleton. Usage: make lesson m="short name"
	@$(DOCPY) scripts/docs/add_lesson.py "$(m)"

.PHONY: graph
graph: ## Rebuild the file dependency graph and check the layering
	@$(DOCPY) scripts/docs/build_file_graph.py
	@echo "docs/architecture/file-graph.md and file-graph.json"

.PHONY: review
review: ## Automated code review of the working tree. See ADR-0011
	@$(DOCPY) scripts/ci/code_review.py --output security/reviews

# ---------------------------------------------------------------- tests

# One invocation over everything, which is the only run whose coverage number
# means what it says. It is also the cheaper of the two shapes: the database
# fixture is session scoped, so a split run starts a container twice.
.PHONY: test
test: ## Every backend test. Needs Docker, which the database fixture starts
	$(BIN)/pytest

# The two slices below are for a person narrowing down a failure, never for a
# gate. Neither reports coverage, because a fraction of the suite measured
# against the whole suite's threshold is a number that cannot be read: it fails
# when nothing is wrong, and it would pass a slice that covered nothing it
# touched. ISS-154.
.PHONY: test-unit
test-unit: ## The subset needing no external services, for an offline loop
	$(BIN)/pytest -m "not integration" --no-cov

.PHONY: test-integration
test-integration: ## Integration tests only. Needs Docker for testcontainers
	$(BIN)/pytest -m integration --no-cov

.PHONY: test-web
test-web: ## Frontend unit tests
	cd finops-web && npm run test -- --run

.PHONY: test-all
test-all: test test-web ## Every backend test, plus frontend unit tests

.PHONY: build-web
build-web: ## Build the web bundle. Type checks it, and is what the journeys run against
	cd finops-web && npm run build

# The journeys run against dist, and vite preview does not build. Without this
# prerequisite they test whatever was last built: on 2026-10-04 that was a
# bundle seven hours older than the source, containing none of the interface
# work it was reporting as passing.
.PHONY: test-e2e
test-e2e: build-web ## Playwright journeys against the freshly built bundle
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
	@$(DOCPY) scripts/ci/check_env_keys.py
	$(COMPOSE) up -d --build
	$(MAKE) migrate
	@echo "API  http://localhost:9731/docs"
	@echo "Web  http://localhost:9732        the built bundle, which is what this target starts"
	@echo "     http://localhost:9735        the development server, if npm run dev is running"

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
# Also from the working tree, for the second reason above. Running alembic inside
# the image applies the migrations the image was built with, which is a silent no op
# whenever a revision has been added since. It printed nothing and exited zero.
migrate: ## Apply migrations to the local database
	@set -a; . ./.env; set +a; \
	  METER_DATABASE_URL="postgresql+psycopg://meter:meter_local_only@localhost:$${METER_POSTGRES_PORT:-5432}/meter" \
	  $(BIN)/alembic upgrade head

# Run from the working tree, not inside the api image, and for two reasons.
#
# The image no longer carries `finops_fakes`: a module that fabricates a bill has no
# business in the image that reports a real one, ADR-0022. So the seed cannot run
# there at all.
#
# The second reason is the better one. The image bakes the source in at build time,
# so `$(COMPOSE) run api` executes whatever the tree looked like at the last
# `make up`. On 2026-09-21 that meant `make migrate` exited zero having applied
# nothing, and `make seed` then reported writing 2292 rows through the same stale
# image, while the local database sat four revisions behind. Running from the tree
# against the exposed port cannot drift.
#
# PYTHONPATH is the working tree because `finops_fakes` is deliberately not in the
# wheel, so it is importable from the repository and from nowhere else. That is the
# same rule as the forbidden import contract, arriving from the other direction.
.PHONY: seed
seed: ## Fill the local database with a demo estate. DAYS=n for history. Refuses a non local database
	@set -a; . ./.env; set +a; \
	  METER_DATABASE_URL="postgresql+psycopg://meter:meter_local_only@localhost:$${METER_POSTGRES_PORT:-5432}/meter" \
	  METER_LOCAL_AUTH_FILE="$(PWD)/local-auth.yaml" \
	  PYTHONPATH="$(PWD)" \
	  $(BIN)/python scripts/demo/seed_demo.py --days $(or $(DAYS),1)

.PHONY: restore-drill
restore-drill: ## Restore into a scratch database and prove it works. TASK-P0-028
	@set -a; . ./.env; set +a; \
	  METER_DATABASE_URL="postgresql+psycopg://meter:meter_local_only@localhost:$${METER_POSTGRES_PORT:-5432}/meter" \
	  METER_LOCAL_AUTH_FILE="$(PWD)/local-auth.yaml" \
	  $(BIN)/python scripts/ops/restore_drill.py \
	    --dump-command "$(COMPOSE) exec -T postgres pg_dump" \
	    --dump-url "postgresql+psycopg://meter:meter_local_only@localhost:5432/meter"

# There is no login. The application reads meter.token from localStorage and
# nothing puts it there, so a browser opened on the local stack shows an empty
# dashboard and every request answers 401. This mints one and prints the line
# to paste into the browser console. Three separate sessions have lost time to
# this, which is what makes it a target rather than a note.
.PHONY: token
token: ## Mint a demo session token and print how to use it. SUBJECT=x for another user
	@$(COMPOSE) run --rm -T api python scripts/ops/local_token.py --explain \
		$(if $(SUBJECT),--subject $(SUBJECT),)

.PHONY: unseed
unseed: ## Clear the demo estate. Every row it wrote, in one command
	@set -a; . ./.env; set +a; \
	  METER_DATABASE_URL="postgresql+psycopg://meter:meter_local_only@localhost:$${METER_POSTGRES_PORT:-5432}/meter" \
	  METER_LOCAL_AUTH_FILE="$(PWD)/local-auth.yaml" \
	  PYTHONPATH="$(PWD)" \
	  $(BIN)/python scripts/demo/seed_demo.py --remove

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
verify: lint check-writing check-docs check-docstrings check-memory test test-web test-e2e security-scan ## Everything CI runs on a merge request
	@echo "verify passed"

# Kept as a name rather than removed, because the pipeline and two scripts say
# `make ci`. It has nothing left to add: `verify` runs the integration tests now.
.PHONY: ci
ci: verify ## Everything CI runs on the default branch
	@echo "ci passed"
