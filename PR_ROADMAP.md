# PR Roadmap – Phase 1

## 1. Purpose

This roadmap is a planning artifact that defines the complete set of pull requests required to implement Phase 1 of the Nexus system. It is not implementation guidance—it is scope control.

**How this document is used:**

- Each PR is sized for LLM-assisted implementation (Claude Sonnet 4.5)
- Each PR maps to explicit sections of the specification in `SPEC/`
- Each PR is dependency-ordered and non-overlapping
- Each PR has clear acceptance criteria and exclusions
- Implementation prompts will be written separately, referencing this roadmap and the spec

This roadmap enforces strict boundaries to prevent PR sprawl, scope creep, and architectural drift.

---

## 2. Principles for All PRs

Every PR in this roadmap adheres to the following invariants:

### One Axis of Change
- Each PR introduces **one** new capability or completes **one** foundational layer
- No PR combines orthogonal concerns (e.g., "users + documents" in one PR)

### Strict Boundaries
- PRs touch 3–8 files, <800 LOC
- Clear "not in this PR" exclusions prevent sprawl
- No speculative features or premature optimization

### Dependency Correctness
- Every PR lists explicit dependencies
- No PR depends on a later PR
- Foundation layers precede features that consume them

### Invariants Enforcement
- Typed IDs enforced at creation time
- Anchor correctness validated in tests
- Visibility and ACL rules applied at query boundaries
- Error envelopes used consistently across all endpoints
- Pagination shape standardized (cursor-based where specified)

### Testing Expectations
- Unit tests for business logic
- Integration tests for API contracts
- Fixture data for end-to-end validation
- Edge case coverage (empty states, boundary conditions)

### API Contract Consistency
- REST conventions followed (verbs, status codes, resource paths)
- OpenAPI spec updated in lockstep with implementation
- Request/response sanitization applied uniformly
- No implicit coercion or silent failures

### Claude-Friendly PR Sizing
- PRs sized to fit within Claude's context window with full spec + codebase awareness
- Implementation can be completed in a single LLM session
- Changes are reviewable and testable as atomic units

---

## 3. Phase Overview

Phase 1 consists of **24 PRs** organized into **8 stages**.

### Stage 0: Bootstrap + Tooling (2 PRs)
Repository structure, CI/CD, linting, formatting, type checking, pre-commit hooks, Docker setup, environment templates.

### Stage 1: Backend Infrastructure (3 PRs)
Database schema with typed IDs, migrations, error envelopes, logging, monitoring primitives, pagination utilities.

### Stage 2: Users + Auth (2 PRs)
Clerk OIDC integration, user creation, JWT validation, protected endpoints, auth middleware.

### Stage 3: Documents + Ingestion (2 PRs)
Document upload, file storage, media detection, text extraction, canonical text storage, chunking.

### Stage 4: Frontend Shell + Integration (2 PRs)
React app setup, routing, layout, Clerk auth wiring, OpenAPI client generation, development seeding.

### Stage 5: Reading + Highlighting + Annotations (4 PRs)
Reading sessions, text highlighting with anchor validation, annotations, persistence and retrieval.

### Stage 6: Retrieval + Embeddings (2 PRs)
Embeddings pipeline, vector storage, BM25 indexing, hybrid search endpoint.

### Stage 7: Conversations + LLM + Vertical Slice (3 PRs)
Conversation management, message storage, LLM integration, RAG pipeline, **first complete vertical slice (upload → highlight → chat)**.

### Stage 8: Links + Hardening (2 PRs)
Document linking, document list/detail frontend, test coverage, production readiness.

---

## 4. Detailed PR Breakdown

---

## Stage 0: Bootstrap + Tooling

### PR 0.1 – Repository + Tooling + CI Bootstrap

**Objective:**
Establish repository structure, development tooling, CI/CD pipeline, and environment configuration templates.

**Dependencies:**
None.

**Deliverables:**
- Repository directory structure:
  - `backend/` (Python, FastAPI)
  - `frontend/` (React)
  - `docs/` (schema, API, deployment)
- Backend tooling (`pyproject.toml` or `setup.py`):
  - black (code formatting)
  - ruff (linting)
  - mypy (type checking)
  - pytest (testing framework + fixtures)
  - isort (import sorting)
- Frontend tooling (`package.json`):
  - eslint (linting)
  - prettier (code formatting)
  - typescript (type checking)
  - jest (testing)
- Docker setup:
  - `docker-compose.yml` for local development (postgres + redis + api + frontend)
  - Postgres configured with pgvector extension
  - Redis configured for Celery broker
- Environment templates:
  - `.env.example` (all required variables: DB, Redis, Clerk keys, LLM keys, API URLs)
  - Backend config loading from environment
- Pre-commit hooks (black, ruff, mypy, isort, prettier)
- CI pipeline (GitHub Actions or equivalent):
  - Backend: lint, format check, type check, pytest
  - Frontend: lint, format check, jest tests

**Acceptance Criteria:**
- `docker-compose up` starts api + postgres + redis without errors
- All services healthy (`postgres ready for connections`, `redis listening`, `api listening on port 8000`)
- `make test` (or equivalent) runs backend tests locally and in CI
- `make lint` + `make typecheck` run and pass locally and in CI
- `make format-check` verifies code without auto-formatting
- Pre-commit hooks block commits with formatting/linting violations
- `.env.example` contains all placeholders (not actual secrets)
- Frontend `bun test` runs and passes

**Out of Scope:**
- Database schema or migrations
- API endpoints
- Authentication logic
- Any business logic

**Spec References:**
- `SPEC/architecture.md` §1.1 (backend: Python/FastAPI/SQLAlchemy)
- `SPEC/architecture.md` §1.2 (PostgreSQL + pgvector)
- `SPEC/architecture.md` §1.3 (Redis + Celery)

---

### PR 0.2 – FastAPI Application Skeleton + Health + Logging Config

**Objective:**
Create FastAPI application skeleton with healthcheck endpoint, structured logging, and global configuration.

**Dependencies:**
PR 0.1 (repository + docker setup).

**Deliverables:**
- FastAPI application initialization (`main.py` or `app.py`)
- Global settings/configuration module:
  - Read environment variables in one place
  - Database URL, Redis URL, Clerk settings, LLM keys
  - Application mode (development, staging, production)
- Healthcheck endpoint:
  - `GET /health` returns `{ "status": "ok" }` (no auth required)
  - Checks database and Redis connectivity
- Structured logging configuration:
  - JSON output with request ID / trace ID
  - Log levels (DEBUG, INFO, WARN, ERROR)
  - Logs include correlation IDs for request tracing
- CORS configuration (permissive for local dev, locked for non-local)
- Basic error handling middleware (catches unhandled exceptions)
- Uvicorn server configuration
- OpenAPI spec endpoint (`GET /openapi.json`)

**Acceptance Criteria:**
- `uvicorn main:app --reload` starts the app on port 8000
- `GET /health` returns 200 with `{ "status": "ok" }` (no auth required)
- App reads configuration from environment variables (no hardcoding)
- Startup logs identify database + Redis connectivity
- All logs include `trace_id` for request correlation
- OpenAPI spec is generated and accessible
- App gracefully handles SIGTERM (shutdown signals)

**Out of Scope:**
- API endpoints (except healthcheck)
- Authentication
- Database operations
- Business logic

**Spec References:**
- `SPEC/architecture.md` §1.1 (FastAPI)
- `SPEC/api_contracts.md` §1.4.2 (health endpoint)

---

## Stage 1: Backend Infrastructure

### PR 1.1 – Database Schema + Typed IDs + Alembic Migrations

**Objective:**
Establish PostgreSQL schema with all Phase 1 tables, typed IDs, indexes, constraints, and migration framework (Alembic).

**Dependencies:**
PR 0.2 (FastAPI app for database connection).

**Deliverables:**
- SQLAlchemy 2.0 models for all Phase 1 tables:
  - `users` (external_user_id from Clerk, email, created_at, updated_at)
  - `documents` (title, file_path/url, canonical_text, media_type, owner_id, visibility, created_at, updated_at)
  - `chunks` (document_id, text, byte_start, byte_end, embedding_id, created_at)
  - `highlights` (document_id, user_id, byte_start, byte_end, created_at)
  - `annotations` (text, attached_to_highlight_id or chunk_id, user_id, created_at, updated_at, deleted_at)
  - `readers` (user_id, document_id, current_position, last_read_at, created_at, updated_at)
  - `conversations` (user_id, title, created_at, updated_at, deleted_at)
  - `messages` (conversation_id, role, content, created_at)
  - `libraries` (user_id, name, visibility, created_at, updated_at)
  - `library_memberships` (library_id, user_id, permission_level)
  - `links` (source_document_id, target_document_id, user_id, link_type, created_at)
- Typed ID column helpers (prefixed: `usr_`, `doc_`, `cnk_`, `hl_`, `ann_`, `rdr_`, `conv_`, `msg_`, `lib_`, `lnk_`)
- Primary keys, foreign keys, unique constraints (e.g., user + document for readers)
- Indexes on query-critical columns (user_id, document_id, created_at, byte ranges for highlights/chunks)
- Alembic migration framework:
  - Baseline migration (initial schema)
  - Migration scripts for up/down
  - Schema versioning
- Connection pool configuration (`sqlalchemy.pool.NullPool` for serverless or `QueuePool` for long-running)
- Schema validation tests (alembic upgrade from base → head succeeds)
- Documentation in `docs/schema.md` (table descriptions, foreign keys, constraints)

**Acceptance Criteria:**
- All tables created with correct columns and types
- Typed IDs generated with correct prefixes on create
- Foreign key constraints prevent orphaned records
- Indexes exist on (user_id, document_id, created_at, byte ranges)
- `alembic upgrade head` succeeds from base
- `alembic downgrade -1` succeeds and undoes migration
- Unit tests validate typed ID generation
- No application code (endpoints, services) in this PR

**Invariants Enforced:**
- All IDs use typed, prefixed format
- Timestamps use UTC (`DateTime(timezone=True)`)
- Soft deletes use `deleted_at` where specified (annotations, conversations, documents)
- Foreign keys have appropriate cascade rules
- Unique constraints prevent duplicates (e.g., one reader per user+document)

**Out of Scope:**
- API endpoints
- Business logic
- Embedding vectors (added in later PR)
- Authentication
- Any triggers or stored procedures

**Spec References:**
- `SPEC/api_contracts.md` §2 (typed IDs)
- `SPEC/architecture.md` §1.1 (SQLAlchemy 2.0 + Alembic)

---

### PR 1.2 – Error Envelope + Logging + Request Tracing

**Objective:**
Implement standardized error envelope, structured logging, request ID middleware, and monitoring hooks.

**Dependencies:**
PR 0.2 (FastAPI app), PR 1.1 (database schema for error/log storage if needed).

**Deliverables:**
- Error envelope response shape (all errors return this format):
  ```json
  {
    "ok": false,
    "error": {
      "code": "auth/unauthorized",
      "message": "Invalid or expired JWT",
      "details": null,
      "trace_id": "req_123456789..."
    }
  }
  ```
- HTTP status code mapping:
  - 400 Bad Request → `validation/*` codes
  - 401 Unauthorized → `auth/unauthorized`, `auth/token_expired`
  - 403 Forbidden → `auth/forbidden`
  - 404 Not Found → `resource/not_found`
  - 409 Conflict → `resource/conflict` (e.g., duplicate email)
  - 415 Unsupported Media Type → `validation/unsupported_media_type`
  - 429 Too Many Requests → `ratelimit/exceeded`
  - 500 Internal Server Error → `server/internal_error`
  - 503 Service Unavailable → `service/unavailable` (LLM API down)
- Global exception handler (catches all unhandled exceptions, returns error envelope, logs event)
- Canonical error codes registry:
  - `auth/unauthorized`, `auth/forbidden`, `auth/token_expired`
  - `resource/not_found`, `resource/conflict`, `resource/invalid`
  - `validation/invalid_field`, `validation/required_field`, `validation/unsupported_media_type`
  - `ratelimit/exceeded`
  - `server/internal_error`
  - `service/unavailable`, `service/timeout`
- Request ID middleware:
  - Generates `trace_id` (format: `req_` + UUID) for each request
  - Propagates through all logs and error responses
  - Available in request context
- Structured logging:
  - JSON log format (one JSON object per line)
  - Includes: timestamp, level, message, trace_id, user_id (if authenticated), endpoint, status_code, latency
  - Logs queryable by trace_id for request tracing
- Sentry integration (placeholder, optional initialization):
  - Wire error middleware to send errors to Sentry
  - Include trace_id in Sentry event

**Acceptance Criteria:**
- All API errors return error envelope (correct code, message, trace_id)
- HTTP status codes match error types
- Logs are valid JSON and queryable
- Trace IDs propagate through all logs for a request
- No stack traces in error responses (logged server-side, not exposed)
- Exception handler catches all uncaught exceptions and returns envelope
- Example: invalid JWT returns 401 with `error.code == "auth/unauthorized"`
- Example: missing required field returns 400 with `error.code == "validation/required_field"`

**Out of Scope:**
- Rate limiting (separate PR)
- Metrics/APM (placeholder only)
- Custom business logic error codes

**Spec References:**
- `SPEC/api_contracts.md` §3 (error envelopes, error codes)
- `SPEC/api_contracts.md` §6 (observability)

---

### PR 1.3 – Pagination Primitives + Query Utilities

**Objective:**
Implement cursor-based pagination utilities and database query helpers.

**Dependencies:**
PR 1.1 (database schema).

**Deliverables:**
- Cursor encoding/decoding:
  - Encode: `cursor = base64(json.dumps({"created_at": timestamp, "id": entity_id}))`
  - Decode: parse and validate cursor format
  - Opaque to client (no predictability)
- Pagination response envelope:
  ```json
  {
    "ok": true,
    "data": [...],
    "pagination": {
      "next_cursor": "eyJjcmVhdGVkX2F0IjogMTcwMDAwMDAwMH0=",
      "has_more": true
    }
  }
  ```
- Query builder helpers:
  - `apply_cursor_pagination(query, cursor, limit=20)` → returns `(items, next_cursor, has_more)`
  - Supports multi-column sort keys (e.g., `created_at DESC, id ASC`)
  - Handles edge cases (empty results, invalid cursors, limit > 100)
- Documentation for pagination usage (examples, edge cases)
- Unit tests for cursor encoding/decoding, edge cases (empty, invalid, boundary)

**Acceptance Criteria:**
- Cursor pagination returns paginated results with `next_cursor` and `has_more`
- Cursors are opaque and unguessable
- Invalid cursors return 400 `validation/invalid_cursor`
- Empty results return `{ data: [], pagination: { next_cursor: null, has_more: false } }`
- Multi-column sort keys work correctly
- Limit > 100 capped at 100 (no DoS)
- Pagination is deterministic (same query, same cursor → same results)

**Out of Scope:**
- Offset-based pagination (cursor-only)
- Filtering or search
- API endpoints (utilities only)

**Spec References:**
- `SPEC/api_contracts.md` §5 (pagination)

---

## Stage 2: Users + Auth

### PR 2.1 – Clerk OIDC Integration + JWT Middleware + User Sync

**Objective:**
Integrate Clerk OIDC provider, validate JWTs, create/sync user records from Clerk tokens.

**Dependencies:**
PR 1.1 (database schema), PR 1.2 (error envelope).

**Deliverables:**
- Clerk OIDC configuration:
  - Fetch Clerk JWKS endpoint
  - Validate JWT signature
  - Extract `sub` (Clerk user ID) from token
- JWT validation middleware:
  - All endpoints except `/health` require valid `Authorization: Bearer <jwt>` header
  - Invalid/expired JWTs return 401 `auth/unauthorized`
  - Malformed headers return 401 with `auth/invalid_header`
- User sync service:
  - Create user record in database on first request (if not exists)
  - Map Clerk `sub` → `users.external_user_id`
  - Extract email from JWT `email` claim
- Protected endpoint decorator:
  - `@require_auth` decorator/dependency for FastAPI routes
  - Injects authenticated user into request context
  - Rejects unauthenticated requests with 401
- Public endpoint exemptions:
  - `/health` is public (no auth required)
  - `/openapi.json` is public (for schema generation)
- Unit and integration tests for JWT validation
- Documentation on auth flow

**Acceptance Criteria:**
- Valid JWT passes validation, authenticated user available in request context
- Invalid JWT returns 401 `auth/unauthorized`
- Missing JWT returns 401 `auth/unauthorized`
- User created in database on first authenticated request
- `user_id` extracted correctly from JWT
- All protected endpoints block requests without valid JWT
- `/health` accessible without auth
- Clerk JWKS endpoint fetched and cached (with expiry)

**Invariants Enforced:**
- All protected endpoints require valid Clerk JWT
- Authenticated user always available in request context
- User records synced from Clerk (not created elsewhere)
- External user IDs immutable

**Out of Scope:**
- User profile creation (email verified, etc.)
- Multi-tenant or organization support
- JWT refresh logic (delegated to Clerk)
- Custom user claims

**Spec References:**
- `SPEC/architecture.md` §1.5 (Clerk OIDC)
- `SPEC/api_contracts.md` §1.4.1 (authentication)

---

### PR 2.2 – Rate Limiting + CORS Configuration + Security Headers

**Objective:**
Implement rate limiting, CORS policy, and basic security headers.

**Dependencies:**
PR 0.2 (FastAPI app), PR 2.1 (auth middleware).

**Deliverables:**
- Rate limiting:
  - Per-user rate limits (configurable, e.g., 100 requests/minute)
  - Per-endpoint limits (stricter for expensive operations like document upload)
  - Token bucket algorithm or sliding window
  - Exceeding limit returns 429 `ratelimit/exceeded` with `Retry-After` header
  - Rate limit info in response headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)
- CORS configuration:
  - Local dev: permissive (allow all origins, methods, headers)
  - Staging/production: whitelist frontend origin(s)
  - Allow credentials (Clerk tokens)
  - Preflight requests cached (Access-Control-Max-Age: 86400)
- Security headers:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `X-XSS-Protection: 1; mode=block`
  - `Strict-Transport-Security: max-age=31536000` (HTTPS only, in prod)
- Rate limit storage (Redis or in-memory for local dev)
- Configuration for rate limit thresholds
- Unit tests for rate limiting logic
- Documentation on rate limit policy

**Acceptance Criteria:**
- Requests within limit succeed normally
- Requests exceeding limit return 429 with `Retry-After` header
- Rate limit headers present in all responses
- CORS allows frontend origin in non-local envs
- CORS preflight requests return correct headers
- Security headers present in all responses
- Rate limits per user (not global)

**Out of Scope:**
- Advanced DDoS protection
- IP-based rate limiting
- Distributed rate limiting across multiple instances (Redis-backed for Phase 1)

**Spec References:**
- `SPEC/api_contracts.md` §1.4 (CORS, security)
- `SPEC/architecture.md` (security considerations)

---

## Stage 3: Documents + Ingestion

### PR 3.1 – Document Upload + Storage + Media Detection + Canonical Text Extraction

**Objective:**
Implement document upload, file storage, media type detection, and text extraction.

**Dependencies:**
PR 2.1 (auth), PR 1.2 (error envelope).

**Deliverables:**
- Document upload endpoint (`POST /documents`):
  - Accepts multipart file + optional metadata (title)
  - Returns typed document ID (`doc_`)
  - User authenticated (owner_id set to current user)
- File storage:
  - Content-addressable storage (hash-based keys) to prevent duplicates
  - Local filesystem (`backend/storage/documents/`) or S3 equivalent
  - File path includes content hash
- Media type detection:
  - Validate MIME type (extension + sniffing)
  - Supported: PDF, EPUB, DOCX, HTML, Markdown, TXT
  - Unsupported formats return 415 `validation/unsupported_media_type`
- Text extraction pipeline:
  - PDF → text via PyMuPDF or pdfplumber
  - EPUB → text via ebooklib
  - HTML → text via BeautifulSoup (strip tags, normalize whitespace)
  - Markdown → text (preserve structure or strip)
  - TXT → as-is (validate UTF-8)
- Canonical text storage:
  - Extract deterministic canonical text (same file → same text)
  - Normalize whitespace (collapse multiple spaces, trim lines)
  - Store in `documents.canonical_text`
  - Document metadata extraction (title, page count if available)
- Visibility enforcement:
  - Documents default to `private`
  - Owner can later change visibility
- Unit tests for each media type extraction
- Integration tests for upload → storage → extraction

**Acceptance Criteria:**
- Upload endpoint accepts PDF, EPUB, DOCX, HTML, Markdown, TXT
- Files stored with content-addressable keys
- Canonical text extracted and stored
- Unsupported formats return 415
- Document IDs typed (`doc_`)
- Visibility defaults to `private`
- Text extraction deterministic (same file → same text)
- Errors in extraction logged, document marked with error status (or rejection)

**Invariants Enforced:**
- All documents belong to a user (owner_id foreign key)
- Canonical text immutable after creation
- No duplicate file storage (content-addressable)
- Media types validated before processing
- File size limits enforced (configurable, e.g., 50MB)

**Out of Scope:**
- Chunking (separate PR)
- Embeddings (later PR)
- OCR for scanned PDFs
- Document sharing beyond owner
- Document deletion
- File compression or optimization

**Spec References:**
- `SPEC/ingestion.md` (document upload, media handling)
- `SPEC/media.md` (media types, text extraction)

---

### PR 3.2 – Chunking Pipeline + Chunk Storage + Anchor Validation

**Objective:**
Implement chunking of canonical text, store chunks with byte offsets, validate anchor correctness.

**Dependencies:**
PR 3.1 (document upload and text extraction).

**Deliverables:**
- Chunking algorithm:
  - Fixed-size chunks (e.g., 512 tokens or 2000 characters) with overlap
  - Or semantic chunking (if available, e.g., via transformers)
  - Deterministic (same text → same chunks)
- Chunk model:
  - Document ID, text, byte_start, byte_end, created_at
  - Chunk IDs typed (`cnk_`)
- Chunk creation (async or sync during document ingest):
  - Extract chunks from canonical_text
  - Validate byte offsets reference valid ranges
  - Store chunks in database
- Anchor validation:
  - Byte offsets (`byte_start`, `byte_end`) must reference valid ranges in `canonical_text`
  - Out-of-bounds offsets rejected with 400 `validation/invalid_anchor`
- Chunk endpoint (`GET /documents/:doc_id/chunks`):
  - List chunks for a document with pagination
  - Returns paginated chunks with byte offsets
- Unit tests for chunking logic (determinism, boundary conditions)
- Integration tests for chunk retrieval

**Acceptance Criteria:**
- Documents chunked after text extraction
- Chunks stored with correct byte offsets
- Anchors validated against `canonical_text`
- Chunk endpoint returns paginated chunks
- Chunk IDs typed (`cnk_`)
- Chunking deterministic (same text → same chunks)
- Invalid anchors rejected with 400

**Invariants Enforced:**
- All chunks have valid anchors (`byte_start` < `byte_end`)
- Chunks do not overlap (unless designed for overlap)
- Chunks immutable after creation
- Anchors reference `canonical_text`, not original file

**Out of Scope:**
- Embeddings (separate PR)
- Search (later PR)
- Chunk updates or deletion
- Chunk metadata beyond byte offsets
- Variable chunk sizes per document type

**Spec References:**
- `SPEC/ingestion.md` §5 (chunking)
- `SPEC/anchors.md` (anchor correctness, byte offsets)

---

## Stage 4: Frontend Shell + Integration

### PR 4.1 – React App Shell + Routing + Clerk Auth Wiring

**Objective:**
Create React application skeleton with routing, layout, and Clerk authentication integration.

**Dependencies:**
PR 2.1 (auth, JWT tokens), PR 0.1 (frontend tooling).

**Deliverables:**
- React application setup:
  - React 18+, TypeScript, React Router
  - Public + protected route guards
  - Layout shell (sidebar, main content area, header)
- Clerk React SDK integration:
  - `<ClerkProvider>` wrapper in App root
  - `useAuth()` hook for JWT token access
  - `useUser()` hook for user info
  - SignIn / SignUp pages (Clerk hosted or embedded)
  - SignOut button
- Page structure:
  - `/` → landing or redirect to `/app`
  - `/auth/sign-in` → Clerk sign-in
  - `/auth/sign-up` → Clerk sign-up
  - `/app` → authenticated app (protected route)
  - `/app/documents` → document list (placeholder)
  - `/app/conversations` → conversation list (placeholder)
- API client setup:
  - OpenAPI TypeScript client generation (from backend spec)
  - Client wired to use Clerk JWT in Authorization header
  - Configured for backend API URL (from env var)
- Design system (minimal):
  - Basic color palette
  - Typography (headings, body, mono)
  - Button, input, card components
  - No heavy CSS framework yet (Tailwind or basic CSS)
- Error boundary component (catches React errors, displays gracefully)
- Loading states (basic spinners)
- Unit tests (basic component tests, auth flow)

**Acceptance Criteria:**
- App starts without errors
- Public routes accessible (sign-in, sign-up)
- Protected routes require authentication
- Authenticated user can sign out
- Clerk JWT token accessible via `useAuth()`
- OpenAPI client generated and usable
- All API calls include Authorization header with JWT
- Layout renders correctly (sidebar, main area)
- Responsive design (mobile-friendly)

**Out of Scope:**
- Document list implementation (separate PR)
- Document viewer (later PR)
- Highlights/annotations UI (later PR)
- Chat UI (later PR)
- Dark mode
- Accessibility (WCAG) optimization (basic compliance only)
- Performance optimization (e.g., code splitting, lazy loading)

**Spec References:**
- `SPEC/architecture.md` §1.4.1 (React, Clerk)
- `SPEC/api_contracts.md` §1 (OpenAPI client)
- `SPEC/frontend.md` (if exists, else adapt from spec)

---

### PR 4.2 – Dev Seeding + Fixtures + Seed Data Command

**Objective:**
Implement development seeding to create test data for manual QA and early UI work.

**Dependencies:**
PR 3.1 (documents), PR 3.2 (chunks), PR 2.1 (users), PR 5.1 (readers, if available).

**Deliverables:**
- `make seed-dev` or `python manage.py seed` command:
  - Create test user (with known credentials or via Clerk test mode)
  - Create sample documents:
    - Small PDF (test_document.pdf)
    - Sample web article (markdown or HTML)
    - Sample EPUB
  - Extract canonical text and chunks for each
  - Create sample highlights for documents
  - Create sample annotations on highlights
  - Optional: pre-populate with sample conversations
- Fixtures module:
  - Reusable test data builders
  - User factory, document factory, chunk factory, etc.
  - Used by unit/integration tests
- Seeding script idempotent:
  - Can be run multiple times without errors
  - Existing data not duplicated
- Documentation:
  - How to run seeding
  - What data is created
  - How to use fixtures in tests

**Acceptance Criteria:**
- `make seed-dev` creates test user + documents + chunks
- All created data is valid (typed IDs, correct references)
- Seeding idempotent (safe to run multiple times)
- Test data visible in UI after seeding
- Highlights and annotations visible on seeded documents

**Out of Scope:**
- Performance testing data (large-scale datasets)
- Automated data generation (fixed test data only)
- Production-like realistic data

**Spec References:**
- Testing best practices (fixture data for reproducibility)

---

## Stage 5: Reading + Highlighting + Annotations

### PR 5.1 – Reading Sessions (Readers) + Session Lifecycle

**Objective:**
Implement reading session management, session creation, updates, and retrieval.

**Dependencies:**
PR 3.1 (documents), PR 2.1 (auth).

**Deliverables:**
- Reader model (session tracking):
  - One reader per (user, document) pair
  - Tracks current_position, last_read_at
  - Timestamps for session lifecycle
- Create reader endpoint (`POST /readers`):
  - Accepts document_id
  - Creates reader for authenticated user + document
  - Returns typed reader ID (`rdr_`)
  - Idempotent (get-or-create)
- Update reader endpoint (`PATCH /readers/:id`):
  - Update current_position
  - Update last_read_at on each request
- Get reader endpoint (`GET /readers/:id`):
  - Retrieve reader with session state
  - ACL: user can only read own reader
- List readers for document (`GET /documents/:doc_id/readers`):
  - List all readers for a document (only readable by owner)
  - Paginated
- Session state tracking:
  - current_position (byte offset or percentage, if supported)
  - last_read_at (timestamp)
  - created_at, updated_at
- Visibility enforcement (users cannot read others' sessions)
- Unit and integration tests

**Acceptance Criteria:**
- Users can create reading sessions for documents
- Reading position tracked (current_position updated)
- Sessions updated on position change
- Reader IDs typed (`rdr_`)
- ACL enforced (users cannot read others' sessions)
- Get-or-create idempotent

**Invariants Enforced:**
- One reader per (user, document) pair
- Readers belong to users (user_id foreign key)
- Readers reference documents (document_id foreign key)

**Out of Scope:**
- Highlights (separate PR)
- Annotations (separate PR)
- Progress tracking (percentage read)
- Reading history analytics
- Device sync (not Phase 1)

**Spec References:**
- `SPEC/readers.md` (reading sessions)
- `SPEC/acl.md` (visibility rules)

---

### PR 5.2 – Highlights + Anchor Validation + Retrieval

**Objective:**
Implement text highlighting with anchor correctness, storage, and retrieval.

**Dependencies:**
PR 5.1 (readers), PR 3.2 (chunks with anchors).

**Deliverables:**
- Highlight model:
  - Document ID, user ID, byte_start, byte_end
  - Optional: chunk reference (denormalization)
  - Created_at timestamp
  - Highlight IDs typed (`hl_`)
- Create highlight endpoint (`POST /highlights`):
  - Accepts document_id, byte_start, byte_end
  - Validates anchors against canonical_text
  - Creates highlight if valid
  - Returns 400 if anchors invalid
- Anchor validation:
  - byte_start < byte_end
  - byte_end <= len(canonical_text)
  - Text at range is valid UTF-8
- List highlights for document (`GET /documents/:doc_id/highlights`):
  - Return all highlights for document (paginated)
  - Include byte offsets
- List highlights for user (`GET /users/:id/highlights`):
  - Return all highlights created by user (across documents)
  - Paginated
- Visibility enforcement:
  - Users can only see their own highlights
- Unit tests for anchor validation
- Integration tests for highlight creation and retrieval

**Acceptance Criteria:**
- Users can create highlights with byte-range anchors
- Anchors validated against `canonical_text`
- Highlights stored with correct offsets
- Highlight IDs typed (`hl_`)
- ACL enforced (users cannot read others' highlights)
- Invalid anchors return 400 `validation/invalid_anchor`

**Invariants Enforced:**
- All highlights have valid anchors (byte_start < byte_end)
- Highlights reference `canonical_text`
- Highlights immutable after creation
- Highlights belong to users and documents

**Out of Scope:**
- Highlight colors or tags
- Highlight deletion
- Highlight sharing
- Highlight updating
- Bulk highlight creation

**Spec References:**
- `SPEC/highlights.md` (highlighting)
- `SPEC/anchors.md` (anchor correctness)
- `SPEC/acl.md` (visibility rules)

---

### PR 5.3 – Annotations + Note Storage + Attachment to Highlights/Chunks

**Objective:**
Implement user annotations (notes) attached to highlights or chunks, with storage and retrieval.

**Dependencies:**
PR 5.2 (highlights), PR 3.2 (chunks).

**Deliverables:**
- Annotation model:
  - Text note content
  - Attached to highlight OR chunk (exactly one)
  - User ID
  - Timestamps: created_at, updated_at, deleted_at (soft delete)
  - Annotation IDs typed (`ann_`)
- Create annotation endpoint (`POST /annotations`):
  - Accepts highlight_id OR chunk_id (mutually exclusive)
  - Accepts text (note content)
  - Creates annotation
  - Returns annotation with ID
- Update annotation endpoint (`PATCH /annotations/:id`):
  - Update text
  - Returns 404 if deleted_at is set
- Delete annotation endpoint (`DELETE /annotations/:id`):
  - Soft delete (set deleted_at)
- List annotations for document (`GET /documents/:doc_id/annotations`):
  - List all annotations for document (not deleted)
  - Paginated
- List annotations for highlight (`GET /highlights/:id/annotations`):
  - List annotations attached to highlight
- List annotations for user (`GET /users/:id/annotations`):
  - List all user's annotations (not deleted)
- Visibility enforcement:
  - Users can only see/edit their own annotations
- Unit and integration tests

**Acceptance Criteria:**
- Users can create annotations on highlights or chunks
- Annotations are editable and deletable (soft delete)
- Annotation IDs typed (`ann_`)
- ACL enforced (users cannot read others' annotations)
- Annotation text required (non-empty)
- Deleted annotations not returned in list endpoints

**Invariants Enforced:**
- Annotations belong to users (user_id foreign key)
- Annotations reference exactly one highlight or chunk (not both)
- Soft-deleted annotations (deleted_at not null)
- Immutable creation time

**Out of Scope:**
- Annotation threading/replies
- Annotation sharing
- Annotation search
- Rich text formatting (plain text only, Phase 1)
- Mention/tagging (@user)
- Annotation reactions/likes

**Spec References:**
- `SPEC/annotations.md` (annotations)
- `SPEC/acl.md` (visibility rules)

---

### PR 5.4 – Frontend: Document List + Detail View

**Objective:**
Implement document listing page and basic document detail view in React.

**Dependencies:**
PR 4.1 (React shell, Clerk auth), PR 3.1 (documents API), PR 4.2 (dev seeding).

**Deliverables:**
- Document list page (`/app/documents`):
  - Fetch documents for authenticated user via API
  - Display in table or list (title, created_at, media_type)
  - Empty state message
  - Loading state (spinner)
  - Error handling (display error message)
  - Pagination controls (next/prev via cursor)
  - Action: click to open document detail
- Document detail view (`/app/documents/:doc_id`):
  - Fetch document metadata via API
  - Display: title, media_type, created_at, owner
  - Show canonical_text preview or full text (if reasonable size)
  - Link back to document list
  - Placeholder for reader (not implemented yet)
- OpenAPI client usage:
  - All fetches via generated client (no raw fetch)
  - Proper error handling (show error envelopes to user)
- Basic styling (responsive, readable)
- Unit tests for components
- Integration tests (mock API, check rendering)

**Acceptance Criteria:**
- Document list loads and displays user's documents
- Pagination works with cursor navigation
- Empty state shown when no documents
- Loading state shown during fetch
- Errors displayed gracefully
- Click document to view detail
- Document detail shows content
- Responsive on mobile (basic breakpoint)
- All API calls via generated client

**Out of Scope:**
- Document upload (comes later)
- Document deletion
- Document sharing
- Full-text search
- Sorting/filtering (basic sort only, if time)
- Document preview/thumbnails
- Bulk actions

**Spec References:**
- `SPEC/frontend.md` (if exists, else adapt from architecture)

---

## Stage 6: Retrieval + Embeddings

### PR 6.1 – Embeddings Pipeline + Vector Storage + BM25 Index

**Objective:**
Implement embedding generation for chunks, vector storage (pgvector), and BM25 full-text index.

**Dependencies:**
PR 3.2 (chunks).

**Deliverables:**
- Embedding generation:
  - OpenAI embeddings API (or Anthropic, or local model via sentence-transformers)
  - Deterministic (same text → same embedding)
  - Idempotent (backfill without duplicates)
- Vector column in chunks table:
  - Add `embedding` column with pgvector type
  - Vector dimension: 1536 (OpenAI) or configured per model
- BM25 full-text indexing:
  - PostgreSQL `tsvector` column on chunks.text
  - GIN index for full-text search
  - Text normalization (stemming, stop words)
- Async embedding job (Celery):
  - Background task to generate embeddings for chunks
  - Triggered after document chunking
  - Retry on failure (e.g., rate limits)
  - Idempotent (upsert embedding if already exists)
- Migration to add embedding column
- Unit tests for embedding generation
- Integration tests for vector storage

**Acceptance Criteria:**
- All chunks eventually have embeddings (dense vectors)
- BM25 index built on text column
- Embeddings generated via external API or local model
- Embedding generation idempotent (same text → same embedding)
- Migration adds vector column without data loss

**Invariants Enforced:**
- All chunks eventually have embeddings
- Embeddings immutable after generation
- BM25 index synchronized with chunk text
- Vector dimension consistent

**Out of Scope:**
- Search endpoints (separate PR)
- Query rewriting
- Retrieval ranking
- Hybrid search logic
- Embedding model fine-tuning
- Batch embedding optimization (beyond Celery)

**Spec References:**
- `SPEC/embeddings.md` (embedding generation, vector storage)
- `SPEC/architecture.md` §1.3 (Celery jobs)

---

### PR 6.2 – Hybrid Search (BM25 + Vector) + Retrieval Endpoint

**Objective:**
Implement hybrid search combining BM25 and vector similarity, with ranked retrieval endpoint.

**Dependencies:**
PR 6.1 (embeddings and BM25 index).

**Deliverables:**
- Search endpoint (`POST /search`):
  - Accepts query string
  - Performs BM25 + vector search
  - Returns ranked chunks with scores
  - Paginated
- BM25 query logic:
  - PostgreSQL full-text search on chunks.text
  - TF-IDF scoring
  - Stop word removal
- Vector similarity query:
  - Embed query string (same model as chunks)
  - pgvector cosine similarity search
  - Top-K results (e.g., 20)
- Hybrid ranking:
  - Combine BM25 + vector scores (e.g., RRF or weighted average)
  - Re-rank by combined score
  - Return top results
- Visibility filtering:
  - Users can only search documents they own
  - Filter results to user's documents
- Pagination for results
- Unit tests for ranking logic
- Integration tests for search endpoint

**Acceptance Criteria:**
- Search endpoint returns ranked chunks
- BM25 and vector scores combined
- Results filtered by user's document access
- Empty queries handled gracefully (error or empty result)
- Pagination works with search results
- Both BM25 and vector matches found

**Invariants Enforced:**
- Search respects ACL (users cannot see others' documents)
- Results are chunks (not documents)
- Ranking deterministic for same query

**Out of Scope:**
- Query rewriting or expansion
- Filters (date, document type)
- Re-ranking with LLM
- Search analytics
- Typo tolerance
- Synonyms or query expansion

**Spec References:**
- `SPEC/retrieval.md` (hybrid search, retrieval)
- `SPEC/embeddings.md` (vector search)
- `SPEC/acl.md` (visibility filtering)

---

## Stage 7: Conversations + LLM + Vertical Slice

### PR 7.1 – Conversation Model + Message Storage + Thread Management

**Objective:**
Implement conversation threads, message storage, and thread lifecycle management.

**Dependencies:**
PR 2.1 (auth), PR 1.1 (schema).

**Deliverables:**
- Conversation model:
  - User ID, title, created_at, updated_at, deleted_at
  - Conversation IDs typed (`conv_`)
- Message model:
  - Conversation ID, role (user/assistant), content, created_at
  - Message IDs typed (`msg_`)
  - Immutable (no updates)
- Create conversation endpoint (`POST /conversations`):
  - Accepts optional title
  - Creates conversation for authenticated user
  - Returns conversation with ID
- List conversations endpoint (`GET /conversations`):
  - List all conversations for user (not deleted)
  - Paginated
  - Sort by updated_at DESC
- Get conversation endpoint (`GET /conversations/:id`):
  - Retrieve conversation metadata
- List messages in conversation (`GET /conversations/:id/messages`):
  - List all messages in conversation (paginated)
  - Ordered by created_at ASC
- Visibility enforcement:
  - Users can only see their own conversations
- Soft delete support (conversations.deleted_at)
- Unit and integration tests

**Acceptance Criteria:**
- Users can create conversations
- Conversations store metadata (title, created_at)
- Messages stored with role, content, timestamp
- Conversation/Message IDs typed
- ACL enforced (users cannot read others' conversations)
- Pagination works for both conversations and messages
- Messages returned in creation order

**Invariants Enforced:**
- Conversations belong to users (user_id foreign key)
- Messages belong to conversations (conversation_id foreign key)
- Messages immutable after creation
- Unique constraint: one title per user per day (or no uniqueness, flexible)

**Out of Scope:**
- LLM integration (separate PR)
- Streaming (separate PR)
- Message editing/deletion
- Conversation editing
- Conversation sharing
- Typing indicators

**Spec References:**
- `SPEC/conversations.md` §1–§2 (conversation model)
- `SPEC/acl.md` (visibility rules)

---

### PR 7.2 – LLM Integration + Prompt Assembly + Message Creation

**Objective:**
Integrate LLM API (OpenAI or Anthropic), assemble prompts with history, generate responses.

**Dependencies:**
PR 7.1 (conversations and messages).

**Deliverables:**
- LLM client:
  - OpenAI API client or Anthropic API client
  - Configured via environment variables (API key, model, base URL)
  - Error handling (rate limits, timeouts, invalid responses)
- Prompt assembly:
  - System prompt (role description, instructions)
  - Conversation history (previous messages in order)
  - Format: structured messages with role/content
- Message creation endpoint (`POST /conversations/:id/messages`):
  - Accepts user message text
  - Creates user message in database
  - Triggers LLM response generation
  - Returns both user + assistant messages
- Response generation:
  - Non-streaming (collect full response before returning)
  - Generate assistant message via LLM
  - Save assistant message to database
  - Return assembled response
- Error handling:
  - LLM API failures return 503 `service/unavailable`
  - Timeouts return 504 `service/timeout`
  - Invalid responses logged and handled gracefully
  - Retry logic (exponential backoff) for transient failures
- Unit tests for prompt assembly (determinism)
- Integration tests for message creation and LLM response

**Acceptance Criteria:**
- Users can send messages to conversations
- LLM generates responses
- User + assistant messages both stored
- LLM errors return appropriate error codes
- Prompts include conversation history
- Same prompt produces same response (deterministic model)
- Response includes both user and assistant messages

**Invariants Enforced:**
- All assistant messages generated by LLM (not created directly)
- User messages immutable after creation
- No user-supplied system prompts (system prompt fixed)

**Out of Scope:**
- RAG integration (separate PR)
- Streaming responses (Phase 2)
- Context pruning (keep all history Phase 1)
- Per-conversation model/temperature configuration
- Custom system prompts per conversation
- Token counting and limits

**Spec References:**
- `SPEC/llm_pipeline.md` §1–§2 (LLM integration, prompt assembly)

---

### PR 7.3 – RAG Pipeline + Context Injection + Vertical Slice E2E (Upload → Chat)

**Objective:**
Integrate retrieval into LLM prompts, implement RAG pipeline, and deliver first complete vertical slice.

**Dependencies:**
PR 7.2 (LLM integration), PR 6.2 (hybrid search).

**Scope:**
This is the first complete **vertical slice**: a user can upload a document, highlight text, add annotations, and chat with an LLM that uses retrieval for context. This PR delivers measurable, end-to-end value.

**Deliverables:**

#### Backend
- RAG pipeline:
  - Query → search chunks → context assembly → LLM prompt
  - Integrated into message creation endpoint
  - Search scoped to document(s) referenced in conversation context
- Context injection:
  - Retrieved chunks added to LLM system prompt or as user message context
  - Format: "Context from your documents: \n{chunks}" or similar
  - Top-K retrieved chunks (e.g., 5)
- Citation tracking:
  - Store which chunks were used in each LLM response
  - Messages ↔ Chunks many-to-many relationship
  - Track retrieval score (relevance) per citation
- Updated message creation endpoint:
  - Before LLM call, retrieve context from documents
  - Inject context into prompt
  - After LLM generates response, save citations
- Error handling:
  - No relevant documents found → still respond (without context)
  - Search failure → fall back to non-RAG response
- Unit tests for context assembly (retrieval + formatting)
- Integration tests for RAG flow (E2E)

#### Frontend
- Document list page: user can upload document (UI)
- Document detail page: displays highlights (if any)
- Highlight creation: user can select text and create highlight
- Annotation UI: user can add note to highlight
- Chat interface:
  - Conversation list on sidebar
  - Messages view in main area
  - Input box to send message
  - Display LLM response
  - Show context (optional: retrieved chunks used in response)
- All wired to backend API

**Acceptance Criteria:**

**Backend:**
- Message creation triggers retrieval before LLM call
- Retrieved chunks injected into LLM prompt
- Citations stored in database (message ↔ chunk links)
- Responses grounded in retrieved context
- Empty retrieval results handled (still respond without context)
- LLM response includes citations (metadata)

**Frontend:**
- User can upload PDF/web article
- Document visible in list immediately
- User can open document and see canonical text
- User can select text and create highlight (persists on reload)
- User can add annotation to highlight
- User can start conversation ("Ask about this document")
- User can send message in conversation
- LLM response displays with retrieved context
- Conversation persists on reload
- Error messages display clearly

**Observable E2E Behavior:**
```
1. User signs in
2. User uploads a PDF about "machine learning"
3. PDF processed: canonical text extracted, chunks created, embeddings generated
4. Document appears in list
5. User opens document, sees text and highlights section (empty)
6. User selects phrase "neural networks" and creates highlight
7. Highlight persists on reload
8. User adds annotation: "Key concept in deep learning"
9. User clicks "Chat about this document"
10. Conversation created
11. User asks: "What is a neural network?"
12. LLM searches document, finds relevant chunks
13. LLM responds with answer grounded in document
14. Response includes citations to document sections
15. Chat history persists
```

**Invariants Enforced:**
- Citations reference actual chunks
- Citations immutable after message creation
- RAG context deterministic for same query
- All API calls use error envelope
- ACL enforced (users cannot see others' documents/chats)

**Out of Scope:**
- Streaming responses (Phase 2)
- Re-ranking with LLM (Phase 2)
- Citation formatting in response UI (just show metadata)
- User feedback on citations (thumbs up/down)
- Multiple documents in one conversation
- Document-specific chat settings

**Spec References:**
- `SPEC/conversations.md` §3–§4 (RAG, message creation)
- `SPEC/retrieval.md` §4–§5 (context assembly, retrieval)
- `SPEC/llm_pipeline.md` (LLM pipeline, RAG)
- `SPEC/frontend.md` (if exists, chat UI, document viewer)

---

## Stage 8: Links + Hardening

### PR 8.1 – Document Linking + Bidirectional References

**Objective:**
Implement document-to-document linking, bidirectional reference tracking, and link metadata.

**Dependencies:**
PR 3.1 (documents).

**Deliverables:**
- Link model:
  - Source document ID, target document ID, link_type, user_id
  - Link types: reference, citation, related (enum)
  - Optional metadata (notes, strength)
  - Link IDs typed (`lnk_`)
  - Created_at timestamp
- Create link endpoint (`POST /links`):
  - Accepts source_doc_id, target_doc_id, link_type
  - Creates bidirectional reference
  - Validates documents exist and belong to user
  - Returns link ID
- List links for document:
  - Incoming links (`GET /documents/:id/links?direction=in`)
  - Outgoing links (`GET /documents/:id/links?direction=out`)
  - Bidirectional links (`GET /documents/:id/links?direction=both`)
  - Paginated
- Delete link endpoint (`DELETE /links/:id`):
  - Remove link (not soft delete)
- ACL enforcement:
  - Users cannot link documents they don't own
- Unit and integration tests

**Acceptance Criteria:**
- Users can create links between documents
- Links stored with type and metadata
- Bidirectional queries work (incoming/outgoing)
- Link IDs typed (`lnk_`)
- ACL enforced (users cannot link others' documents)
- No duplicate links (unique on source + target)

**Invariants Enforced:**
- Links reference valid documents (foreign keys)
- Links belong to users (user_id foreign key)
- No self-links (source != target)
- No duplicate links

**Out of Scope:**
- Automatic link extraction (ML-based)
- Link suggestions
- Link annotations
- Graph visualization/API
- Link weighting (Phase 2)

**Spec References:**
- `SPEC/links.md` (document linking)
- `SPEC/acl.md` (visibility rules)

---

### PR 8.2 – Test Coverage + Fixtures + Production Readiness

**Objective:**
Achieve comprehensive test coverage, create fixture data, finalize production readiness.

**Dependencies:**
All prior PRs (this is a hardening PR).

**Deliverables:**
- Unit test coverage >80% for business logic:
  - Error handling, validation, edge cases
  - Typed ID generation
  - Anchor validation
  - Pagination logic
  - Chunking determinism
  - Embedding generation
  - Retrieval ranking
- Integration test coverage for all API endpoints:
  - Happy path (valid input)
  - Error cases (invalid input, 404s, ACL violations)
  - Edge cases (empty results, large payloads, boundary conditions)
  - Full workflows (upload → chunk → search → chat)
- Fixture data (test users, documents, chunks, highlights, annotations, conversations):
  - Reusable across tests (factories)
  - Minimal dependencies
  - Cleanup after tests (no test pollution)
- End-to-end test suite:
  - Vertical slice: upload → highlight → chat (scripted)
  - Browser-based (Selenium, Cypress) or API-based
- CI pipeline finalization:
  - Test runner configured and passing
  - Linter/formatter checks automated
  - Type checking automated
  - All tests run on every commit/PR
  - Coverage reporting
- Configuration management:
  - All secrets externalized (environment variables)
  - No hardcoded API keys, database URLs, etc.
  - `.env.example` complete with all required variables
- Health check improvements:
  - `/health` checks database, Redis, LLM connectivity
  - `/ready` checks all services ready for traffic
- Logging + monitoring configuration:
  - Sentry configured (optional, can be disabled)
  - Structured logging queryable
  - Request tracing via trace_id
- Documentation:
  - `docs/testing.md` (how to run tests, write new tests)
  - `docs/deployment.md` (deployment steps, environment vars, migrations)
  - `docs/api.md` (API overview, common patterns, auth flow)
- Frontend test coverage:
  - Unit tests for components (rendering, user interaction)
  - Integration tests (API mocking, workflows)
  - Basic E2E test (user flow: sign-in → upload → chat)

**Acceptance Criteria:**
- All endpoints tested (happy path + error cases)
- Edge cases covered (empty states, invalid input, ACL violations)
- Fixtures support reproducible tests
- CI passes on all commits
- Test suite runs in <5 minutes
- >80% code coverage for business logic
- All secrets externalized
- Health checks comprehensive
- Logging queryable
- Documentation complete

**Out of Scope:**
- Performance testing/load testing (Phase 2)
- Security audits (Phase 2)
- Accessibility testing (Phase 2)
- Penetration testing (Phase 2)
- Monitoring dashboards (Phase 2)

**Spec References:**
- All spec sections (validation of implementation)

---

## 5. Cross-PR Invariants

The following invariants must hold across **all PRs** in Phase 1:

### Anchor Correctness
- All byte-range anchors (`byte_start`, `byte_end`) reference `canonical_text`
- Anchors validated at creation time (highlights, chunks)
- Invalid anchors rejected with 400 Bad Request

### Visibility & ACL
- All resources (documents, readers, highlights, annotations, conversations) belong to a user
- Users cannot read, modify, or delete others' resources
- ACL checks enforced at query boundaries (not in business logic)

### Typed IDs
- All entity IDs use prefixed, typed format (`usr_`, `doc_`, `cnk_`, `hl_`, `ann_`, `rdr_`, `conv_`, `msg_`, `lnk_`)
- IDs generated at creation time
- IDs are globally unique and non-guessable

### Error Envelopes
- All errors return JSON envelope: `{ ok: false, error: { code, message, details, trace_id } }`
- HTTP status codes consistent with error types
- No stack traces in production responses

### Pagination Shape
- All list endpoints use cursor-based pagination
- Response shape: `{ ok: true, data: [], pagination: { next_cursor, has_more } }`
- Invalid cursors return 400 Bad Request

### No Resource Leaks
- Files uploaded are stored with content-addressable keys
- Orphaned files cleaned up or managed
- Database connections returned to pool
- No unbounded memory growth

### Deterministic Canonical Text Extraction
- Same file → same `canonical_text`
- Extraction reproducible across runs
- Text extraction errors logged and reported

### Clerk Integration
- All authenticated users have `external_user_id` from Clerk
- JWT validation uses Clerk JWKS endpoint
- User creation happens on first authenticated request
- Tokens from Clerk accepted and validated

---

## 6. LLM-Oriented PR Rules

This roadmap is designed for LLM-assisted implementation using Claude Sonnet 4.5.

### PR Sizing for Claude
- Each PR touches 3–8 files, <800 LOC
- Changes fit within Claude's context window with full spec + codebase
- Implementation completable in a single LLM session

### Spec Mapping
- Each PR explicitly references spec sections
- Implementation prompts (written later) will cite spec + roadmap
- No ambiguity in requirements

### Implementation Prompts (Not in This Document)
- Prompts will be written separately, per PR
- Prompts will reference this roadmap + spec sections
- Prompts will include acceptance criteria and exclusions

### Atomic Units
- Each PR is reviewable and testable independently
- No "half-done" states
- PRs merge to main only when complete

---

## 7. Final Summary

This roadmap is a **planning artifact**—not implementation guidance.

**What this roadmap defines:**
- 24 PRs, dependency-ordered
- Clear scope boundaries and exclusions
- Acceptance criteria for each PR
- Invariants enforced across all PRs
- Mapping to specification sections

**What this roadmap does NOT contain:**
- Code
- Endpoint definitions
- File layouts
- Implementation details

**Next steps:**
1. Review this roadmap for completeness and correctness
2. Validate dependency ordering
3. Begin writing implementation prompts for Stage 0 PRs
4. Execute PRs sequentially, starting with PR 0.1

This roadmap is the authoritative sequencing for Phase 1 implementation.
