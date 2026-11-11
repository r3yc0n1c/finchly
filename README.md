# Finchly

Finchly converts semi-structured business documents (electricity/DISCOM bills, textile supplier invoices, purchase orders, delivery challans) into **validated, auditable, ERP-ready records**.

**Core Principles:**
- Local-first inference (zero recurring cost).
- Deterministic validation (arithmetic is never delegated to models).
- Evidence-backed extraction (every field links to normalized bounding boxes and source text).
- Human approval of exact versions before ERP delivery (drafts only in v1).
- Enforced multi-tenancy with PostgreSQL Row-Level Security (RLS).

---

## 1. Quickstart (NFR-001, NFR-003)

### Prerequisites
- Python 3.12+ and `uv`
- Node.js 24+ and `pnpm`
- Docker or Podman with Compose support

### Setup & Verification
```bash
# 1. Setup local environment & install dependencies
make setup

# 2. Run quality checks (format, lint, typecheck, secret scan, tests)
make check

# 3. Start default infrastructure (PostgreSQL 18, NATS JetStream 2.15, Chainguard MinIO, API)
make up

# 4. Probe service health and cluster readiness
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/readyz
```

---

## 2. Monorepo Structure (Spec §19)

```text
finchly/
├── apps/
│   ├── api/            # FastAPI control plane (/healthz, /readyz, /api/v1)
│   └── web/            # Next.js 16 review console (React 19, Biome)
├── packages/
│   ├── domain/         # Pure domain schemas, lifecycle, error catalogue (framework-free)
│   └── contracts/      # OpenAPI specifications & JSON Schemas
├── infra/
│   └── compose/        # Docker Compose definitions & service profiles
├── docs/               # Specifications, ADRs, PRD, and C4 architecture diagrams
├── tests/              # Unit, contract, integration, and security test suites
├── scripts/            # Automation & document integrity linters
└── Makefile            # Standard development targets
```

---

## 3. Development Commands

| Command | Action |
|---|---|
| `make check` | Runs lint, typecheck, secret scan, and all tests |
| `make format` | Formats Python (Ruff) and Web (Biome) code |
| `make lint` | Runs Ruff, doc linter, import-linter, and Biome lint |
| `make typecheck` | Runs Mypy and TypeScript compiler (`tsc --noEmit`) |
| `make test-unit` | Executes Pytest and Vitest test suites |
| `make secret-scan`| Runs `detect-secrets` against `.secrets.baseline` |
| `make openapi` | Regenerates `packages/contracts/openapi.json` from API |
| `make up` | Starts default Compose stack (`postgres`, `nats`, `minio`, `api`) |
| `make down` | Stops Compose stack |
| `make logs` | Tails Compose service logs |

---

## 4. Architecture & Quality Constraints

- **Domain Isolation (NFR-006):** `finchly_domain` contains zero imports from web frameworks (`fastapi`), ORMs (`sqlalchemy`), message brokers (`nats`), or external SDKs. Enforced via `import-linter`.
- **OpenAPI Drift (NFR-004):** Any route or schema change must be reflected in `packages/contracts/openapi.json`. Contract tests enforce this in CI.
- **Continuous Integration (NFR-007):** Pipeline orchestrated via CircleCI (`.circleci/config.yml`), executing format checks, linter, Mypy typechecking, architecture boundaries (`import-linter`), secret scanning, unit tests, and OpenAPI contract drift tests.
- **Security (SEC-015):** No credentials, real documents, or secrets in git. Enforced via pre-commit and CI secret scanning.
