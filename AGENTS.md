# AGENTS.md — Finchly Engineering Rules

Place this file at the repository root as `AGENTS.md`. It extends the Execution Playbook rules; where they differ, the stricter rule applies. If a rule here conflicts with an approved ADR, stop and propose a new ADR — do not choose silently.

## 1. Project overview
Finchly converts semi-structured business documents (v1: electricity/DISCOM bills; textile supplier invoices, purchase orders, delivery challans) into **validated, auditable, ERP-ready records**. Principles: local-first inference, deterministic validation, evidence-backed extraction, human approval of exact versions, auditable transformations, reliable ERP delivery (drafts only in v1), reproducible evaluation, $0 recurring cost.
Assumptions (ADR-010): India-first, English-language documents, INR default.

## 2. Architecture
Modular monolith with separate worker processes (ADR-007). PostgreSQL is the source of truth; NATS JetStream carries work via a **transactional outbox** (ADR-006); S3-compatible object storage holds originals and derived artifacts; no DB transaction is held across OCR, model or ERP calls.
Pipeline stages are separate and individually observable:
`intake → fingerprint/dedupe → page model → text-layer decision/OCR → layout → classify → extract (model, raw text only) → normalize (deterministic) → evidence verify → validate (deterministic) → route → human review → approve → map/preflight → ERP draft → readback/reconcile`.
Decisions: ADR-009 (tenancy/auth), ADR-010 (canonical schema), ADR-011 (phases). Read them before coding.

## 3. Technology choices
Python 3.12+ with FastAPI, SQLAlchemy/Alembic, Pydantic, pytest, Hypothesis, Ruff, mypy/pyright; TypeScript strict with Next.js, Biome, Vitest, Playwright; PostgreSQL with forced RLS; NATS JetStream; MinIO or another S3-compatible store behind an adapter (licence review: ADR-016); Tesseract baseline OCR, PaddleOCR optional profile; llama.cpp behind an adapter (model per ADR-013); OpenTelemetry. **All free/open source; no paid services.** Licence status of each dependency must be recorded before release (ADR-016). Do not add a dependency without recording its licence in `docs/LICENSES.md`.

## 4. Domain boundaries
```
packages/domain      schemas, lifecycle, validation interfaces (no framework imports)
packages/validation  pure deterministic rules
packages/normalization  pure parsers
packages/provenance  evidence resolver + value-support verifier
packages/packs/*     electricity, textile (depend on domain/validation only)
packages/reconciliation  matching (consumes validated versions)
packages/connectors  ERP protocol + adapters (isolated)
apps/api, apps/worker, apps/web   composition and IO
```
Forbidden: domain importing FastAPI, SQLAlchemy, NATS, llama.cpp bindings, OCR engines or ERP SDKs (enforced by import-linter). Extraction never imports connectors. Connectors never import extraction.

## 5. Repository conventions
`main` is always releasable; short-lived branches; small commits; Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `perf:`, `chore:`). Layout per spec §19. Generated artifacts (JSON Schema, OpenAPI, state diagrams) are committed and CI fails on drift. Never commit secrets, private keys, real customer documents or personal data.

## 6. Coding standards
Type hints everywhere; Ruff + mypy/pyright clean; TS strict. Money is `Decimal` (string in JSON/UI); never float. Pure functions for domain logic. Explicit timeouts on every network call. Structured logging with redaction. No broad `except Exception` that hides failures. Errors carry stable codes from the error catalogue. Time from the database/clock interface, not ad hoc.

## 7. Database migration policy
Alembic migrations are reviewed, forward-tested and tested on a disposable database; rollback implications documented in the PR. Every tenant-owned table has `tenant_id`, composite FKs and forced RLS (ADR-009); the migration lint rejects violations. Never edit an applied migration. Destructive changes need a two-step migration and an ADR. App role cannot bypass RLS; audit table forbids UPDATE/DELETE for the app role.

## 8. API contract policy
`/api/v1`; OpenAPI generated from code and committed; contract tests fail on undeclared changes. Breaking change = new version + changelog + owner review. Tenant comes from authenticated context, never from the body. All object access is authorized server-side; IDOR tests are generated from the route table. Error codes are cataloged (e.g., `DUPLICATE_DOCUMENT`, `ENCRYPTED_PDF`, `EXTRACTION_INVALID`, `EVIDENCE_NOT_FOUND`, `APPROVAL_STALE`, `MAPPING_MISSING`). Optimistic concurrency via `expected_version` for user commands.

## 9. Extraction pipeline rules
1. **Never treat model output as validated business data.** It is untrusted input until it passes schema parsing, normalization, evidence verification and deterministic validation, and a human approves.
2. The model returns **raw text only** plus evidence references; normalized values come from deterministic, versioned normalizers; arithmetic is never delegated to the model.
3. Reject (do not repair) malformed, truncated, extra-key or schema-invalid output → `EXTRACTION_INVALID`.
4. Absent means `missing`, never zero or a default.
5. The model has no tools, no network and no cross-document context. Document text is delimited and treated as hostile.
6. Embedded PDF text is used only after the text-layer quality check; invisible text is excluded or flagged.
7. Keep extraction, normalization, validation and ERP delivery separate modules with separate tests.
8. Pin model digest, quantization, llama.cpp version, prompt version, schema version and decoding parameters; record them in `model_runs`. Reprocessing with identical pinned inputs must reproduce deterministic components; model-output differences are stored and diffable.
9. Confidence: never present model self-reported confidence as a probability; calibrated confidence is `null` until ADR-014 criteria are met.

## 10. Evidence provenance requirements
Every field carries: raw text, normalized value (+ normalizer version), page, bounding box in **original-page normalized coordinates**, source engine and `text_source` (embedded/ocr), method (`embedded|ocr_llm|rules|derived|human`), support status, validation status link, and correction history. Evidence references must resolve to persisted blocks (`EVIDENCE_NOT_FOUND` otherwise). A **value-support check** must confirm the value is derivable from the cited text; derived fields record lineage. Never claim evidence exists because a reference is syntactically valid.

## 11. Validation rules
Validators are pure, versioned, deterministic and produce structured issues (`rule_key`, severity, field paths, expected, observed). Missing components are `unknown`, not zero. Wording must not claim legal/tax compliance, GST registration validity, or that a bill is “correct”; use “consistent with configured tariff”, “structure valid”. Tolerances and rounding come from documented policies (ADR-021). Fuzzy matches are candidates only.

## 12. Human review rules
Automated extraction never approves. Corrections create new immutable versions (append-only chain) with reason codes and trigger revalidation. Approval binds {version, RFC 8785 payload hash, validation run, mapping version}; any change makes it stale (`APPROVAL_STALE`). Error-severity issues block approval unless an authorized role records an override with reason. Approver ≠ last corrector by default. Reprocess yields a candidate version and invalidates pending approvals. All actions are audited.

## 13. ERP connector interface
One protocol (`packages/connectors`): capability flags; pure deterministic `map_document`; `preflight`; `create_draft`; `lookup_by_reference`; `readback`; classified errors. Rules:
- Declare a capability only with a passing contract test; otherwise it is `assumed`/`unsupported` in `docs/erp/CAPABILITY_MATRIX.md`. **Never invent ERP API behavior** — implement only what a spike or documentation observed, and record the source.
- Model or document content can never choose host, doctype, model, company or field mapping. Egress only to the deployment-level allowlist; no redirects; IP pinning; timeouts; size caps.
- Credentials envelope-encrypted, write-only, never logged.
- v1 creates **drafts**; never label them “posted”.
- Idempotency key `(tenant, document, connection, purpose)` with payload hash; unique constraints; stale `in_flight` → `unknown_outcome`; reconcile by reference; absence authoritative only if the connector declares it.
- Per-connection concurrency (default 1).

## 14. Testing requirements
Pyramid: unit (pure domain, state machines) → contract (API schemas, adapters) → integration (disposable Postgres/NATS/MinIO/ERP containers) → E2E → load → fault injection → security. Every feature needs happy path, invalid input, authorization/tenant boundary and failure/retry tests. Use Hypothesis for arithmetic, state machines and Decimal logic. Golden-document tests use CER thresholds (not exact OCR equality); LLM tests use recorded fixtures in CI plus a small live smoke set. Never remove or weaken a test; never claim a feature passes without end-to-end verification.

## 15. Benchmark requirements
Deterministic workload generator; warm-up and ≥3 repeated runs; machine/software/model metadata; p50/p95/p99; throughput, error rate, CPU/RAM/VRAM; raw JSON/CSV + Markdown report; baseline comparison. Separate inference time from infrastructure time. Label every result with its **evidence tier** (T1/T2/T3). Never aggregate unrelated document types into one score. Never fabricate targets; thresholds are frozen by committed hash before sealed-test use. Run a smoke workload before any full run.

## 16. Security requirements
Deny by default; server-side authorization on every object access; RLS enforced; Argon2id and server-side sessions (ADR-009); validate uploads by content with documented limits; parse untrusted files only in the no-network sandbox; scan adapter hook; protect against SSRF, path traversal, zip/PDF bombs and XXE; least-privilege service accounts; audit approvals, config changes, exports and ERP actions; document retention and deletion; no secrets or document content in logs, metrics labels or error messages. Do not claim a control exists because a configuration option exists.

## 17. Git workflow
Branch per issue: `feat/FIN-123-short-title`. Commit early, use Conventional Commits, reference the issue ID. PR checklist: tests added, commands run with output, docs/PROGRESS.md/FEATURES.json updated, OpenAPI/ADR updated if applicable, traceability unaffected or updated, security/tenant tests included. Squash only when history adds no value; never force-push `main`.

## 18. Definition of Done (Standard DoD)
A change is Done only when all are true:
1. Requirements and acceptance criteria of the issue are restated and met with evidence.
2. Unit, contract/integration and failure-path tests exist and pass; authorization and tenant-boundary tests exist where relevant.
3. Format, lint, type-check pass; CI green.
4. Observability exists for the new behavior (correlation ID, metrics, redacted logs).
5. Migrations tested forward and on a disposable DB; rollback implications noted.
6. API/schema/OpenAPI and docs updated; ADR added if a material decision changed.
7. `docs/PROGRESS.md` and `docs/FEATURES.json` updated; traceability links valid.
8. A human can reproduce the behavior from a clean checkout.
9. Known gaps and risks are written down; no unsupported claim in docs.

## 19. Task protocol
Read README, the phase, the issue, ADRs and PROGRESS.md → restate acceptance criteria → inspect code → list files/tests/migration/security implications → implement the smallest vertical slice → run all checks → update docs → commit → report: changed files, commands run, results, known gaps, next smallest task → **stop**.
