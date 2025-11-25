# Architecture & Infrastructure

## 1. System Architecture Overview

The system is a **reading-first knowledge management and LLM-chat platform** with a clear separation between backend and frontend tiers.

### 1.1 Backend: Python/FastAPI + SQLAlchemy 2.0 + Alembic

The authoritative backend written in Python (3.11+) using FastAPI framework:

- **Responsibility**: All canonicalization, ingestion, chunking, embedding, remapping, LLM context assembly
- **Auth**: JWT verification against Clerk JWKS endpoint
- **No state**: Stateless workers for horizontal scaling
- **Database**: Single PostgreSQL instance (Supabase as managed Postgres) for all persistent state
- **ORM**: SQLAlchemy 2.0 (ORM + Core) as canonical persistence layer
- **Migrations**: Alembic for all schema migrations
- **Jobs**: Celery workers for async ingestion, embedding, remapping pipelines

**Critical**: SQLAlchemy ORM models are the **single source of truth** for database schema. Direct SQL is allowed only via SQLAlchemy Core for hot paths. Database-first or hybrid modeling is forbidden.

**Why Python?**:
- Rich ecosystem for PDF extraction (PyMuPDF fitz), NLP (transformers), embeddings (sentence-transformers)
- Strong async support via FastAPI / asyncio
- Deterministic extraction simplifies testing and reproducibility
- SQLAlchemy 2.0 provides type safety, async ORM, and robust migration tooling

### 1.2 Database: PostgreSQL + pgvector

Single authoritative PostgreSQL database (Supabase recommended):

- **Canonical state**: All user data, media, highlights, annotations, conversations
- **Vectors**: pgvector extension for embedding storage and similarity search
- **Transactions**: ACID guarantees for highlight creation/remapping operations
- **Indexing**: Gin/GiST indices for JSON, IVFFlat for vectors

**No cache layer**: In Phase 1, all queries hit Postgres directly. Caching (Redis, CDN) deferred to Phase 2.

### 1.3 Job Queue: Redis + Celery

Committed architecture for background jobs:

- **Broker**: Redis (same instance for queue + result backend)
- **Framework**: Celery (Python async job queue)
- **Named queues**: `ingestion`, `embedding`, `remap`, `conversation` (optional for priority)
- **Workers**: Horizontal scaling of Celery workers

**Why Celery?**:
- Tight integration with Python backend
- Flexible routing and concurrency control
- Built-in retry, idempotency, dead-letter handling
- Well-tested for document processing pipelines

**Not RQ/Huey**: Celery chosen for its maturity in multi-step workflows (ingest → canonicalize → chunk → embed → remap).

### 1.4 Frontend

#### 1.4.1 Web Frontend (React) — Phase 1

Standard React application targeting the browser DOM:

- **Framework**: React 18+
- **PDF rendering**: pdf.js library for client-side rendering and text selection
- **Text selection**: Standard DOM `Selection` API for EPUB/web articles
- **State management**: React Query (TanStack Query) for server state, Zustand for UI/local state
- **HTTP client**: Generated from OpenAPI schema or hand-written (React Query / SWR for data fetching)
- **Authentication**: Clerk React SDK for login/logout flows
- **Highlight rendering**: DOM span wrapping for HTML/EPUB (not canvas), canvas overlays for PDFs only

**Phase 1 scope**: Web-only. Mobile support via responsive design, not native apps.

#### 1.4.2 Mobile Frontend (Future — Phase 3+)

Native mobile application using React Native (deferred):

- Will be planned in Phase 3+ only
- Not part of Phase 1 specification

### 1.5 Authentication: Clerk (OIDC / JWTs)

All user authentication delegated to Clerk:

- **User creation**: Happens via Clerk dashboard or sign-up flow
- **JWT tokens**: Clerk issues signed JWTs
- **Verification**: Backend verifies JWT signature using Clerk's JWKS endpoint
- **User mapping**: JWT `sub` claim mapped to `users.external_user_id` in database
- **No password handling**: All password logic, MFA, social auth delegated to Clerk
- **Token refresh**: Client-side Clerk SDKs handle refresh flow

**Token structure**:

```json
{
  "iss": "https://[clerk-instance].clerk.accounts.com",
  "sub": "user_abc123...",
  "aud": "[api-audience]",
  "iat": 1700000000,
  "exp": 1700003600,
  "email": "user@example.com"
}
```

Backend extracts `sub` claim as `external_user_id`, uses internal `users.id` (UUID) for all FK references.

---

## 2. Data Flow

### 2.1 Ingestion Pipeline

```
[User] → [Web/Mobile UI]
           ↓
      [Document Upload]
           ↓
      [FastAPI /documents POST]
           ↓
      [S3 Upload]
           ↓
      [Create document row, status='pending']
           ↓
      [Enqueue ingest_document job]
           ↓
      [Celery Worker: ingest_document]
           ├─ Download from S3
           ├─ Hash blob
           └─ Update document, enqueue canonicalize_document
           ↓
      [Celery Worker: canonicalize_document]
           ├─ Extract canonical text
           ├─ Extract structure
           ├─ Update document, status='ready'
           ├─ If version changed: enqueue remap_highlights
           └─ Enqueue chunk_and_embed_document
           ↓
      [Celery Worker: chunk_and_embed_document]
           ├─ Chunk canonical text
           ├─ Embed chunks
           └─ Write to content_chunks
           ↓
      [User sees document in UI]
```

### 2.2 Highlight Creation

```
[User selects text in reader]
           ↓
[Frontend computes anchor: text_start, text_end, quote, prefix, suffix]
           ↓
[FastAPI /highlights POST]
           ├─ Validate anchor integrity
           ├─ Check Visible(user, media)
           ├─ Write highlight row
           └─ Return highlight
           ↓
[UI renders highlight inline]
```

### 2.3 Retrieval + LLM Chat

```
[User sends message in conversation]
           ↓
[FastAPI /conversations/{id}/messages POST]
           ├─ Validate message content
           ├─ Save message to database
           └─ Trigger context assembly in background (optional)
           ↓
[Async: assemble_context(conversation_id, user_id, message_text)]
           ├─ Retrieve embeddings: content_chunks, thought_chunks, metadata_chunks
           ├─ Filter by Visible(user, source_object) at application layer
           ├─ Assemble LLM context (system message + history + retrieval)
           ├─ Call LLM API (OpenAI, Anthropic, Google)
           └─ Stream/write response
           ↓
[UI displays assistant response]
```

### 2.4 Remapping (on hash change)

```
[Document canonicalize_document completes]
           ↓
[If anchored_content_hash differs from current canonical_hash]
           ├─ Enqueue remap_highlights(document, old_hash, new_hash)
           └─ Do not block canonicalize completion
           ↓
[Celery Worker: remap_highlights]
           ├─ Load all highlights with old_hash
           ├─ For each highlight:
           │  ├─ Exact match search in new canonical_text
           │  ├─ If no match: fuzzy search (≤10% edit distance)
           │  ├─ If match found: update text_start, text_end, hash
           │  └─ If no match: mark is_detached=true
           └─ Log metrics
           ↓
[Detached highlights appear in "Orphaned Highlights" section]
```

---

## 3. Deployment Model

### 3.1 Backend Services

| Service | Technology | Scaling | Notes |
|---------|-----------|---------|-------|
| API | FastAPI | Horizontal (container, K8s) | Stateless, standard auto-scale |
| Celery Workers | Python/Celery | Horizontal | Task-specific queues for priority |
| Redis | Redis | Single instance | Broker + result backend; upgrade to cluster for HA |
| PostgreSQL | Postgres + pgvector | Vertical (RDS) | Connection pooling via PgBouncer |

### 3.2 Frontend Deployment

- **Web**: Static site hosting (Vercel, Netlify, S3 + CloudFront)
- **Mobile**: App Store (iOS) and Play Store (Android) via standard CI/CD

### 3.3 Configuration & Secrets

Environment variables:

```bash
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
CLERK_API_KEY=...
CLERK_JWKS_URL=...
OPENAI_API_KEY=...
EMBEDDING_API_KEY=...
S3_BUCKET=...
S3_REGION=...
ENVIRONMENT=production|staging|development
```

All secrets stored in secure vault (AWS Secrets Manager, Vercel Secrets, etc.). Never committed.

---

## 4. Infrastructure Decisions

### 4.1 Single Database

- **Why**: Single source of truth, ACID guarantees for concurrent operations
- **Risk**: Single point of failure
- **Mitigation**: RDS automated backup, read replicas for analytics, Point-In-Time Recovery (PITR)

### 4.2 Async Database Access via SQLAlchemy

- **FastAPI**: Uses async SQLAlchemy engine with connection pooling
- **Celery**: Uses separate SQLAlchemy engine/session factory for background jobs
- **Connection pooling**: Managed by SQLAlchemy (configurable pool size and timeout)
- **Benefit**: Efficient resource utilization, non-blocking DB access, no connection exhaustion

### 4.3 PDF Anchoring: pdf.js + pdf_file_hash

- **Why pdf.js offsets** (not canonical text byte offsets): Allows extraction code updates without breaking anchors
- **PyMuPDF (fitz)**: Used for canonical text extraction (primary extractor)
- **pdf_file_hash**: Triggers remap only if PDF binary changes, not extraction code
- **Tradeoff**: Remap algorithm only works for text-extractable PDFs; scanned documents cannot be remapped

### 4.4 Three Embedding Spaces

- **Reason**: Allows boosting user's own thoughts, metadata, and content independently
- **Scaling**: Each space may have different re-embedding cadence, model versions
- **Retrieval**: Results from all spaces weighed and merged (see [spec/embeddings.md](embeddings.md))

---

## 5. HTML Sanitization & Content Security

### 5.1 Sanitization Ruleset

All user-facing HTML content MUST be sanitized before rendering using an allowlist-based approach:

**Allowed HTML elements**:

```
p, h1, h2, h3, h4, h5, h6, em, strong, a, ul, ol, li, code, pre, blockquote, span, div
```

**Disallowed**:

- `<script>`: MUST be removed (and content discarded)
- `<style>`: MUST be removed (inline styles stripped)
- `<iframe>`: MUST be removed
- `on*` attributes (onclick, onload, etc.): MUST be removed
- `<object>`, `<embed>`, `<applet>`: MUST be removed
- SVG with script handlers: MUST be sanitized or removed
- `<form>`, `<input>`, `<button>`: MUST be removed (to prevent hijacking)

**Safe attributes**:

```
href (a), id, class, title, data-* attributes
```

**Implementation**:

Use Bleach (Python) or equivalent sanitizer:

```python
import bleach

ALLOWED_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'em', 'strong',
                'a', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote', 'span', 'div']
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'id', 'title'],
    '*': ['id', 'class', 'data-*']
}

def sanitize_html(html: str) -> str:
    return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
```

### 5.2 Sanitization Applied To

Sanitization MUST be applied to:

1. **EPUB HTML fragments**: Before rendering in reader
2. **Web article HTML**: Before storing and displaying
3. **Rendered markdown HTML**: Output of markdown → HTML pipeline MUST be sanitized

**Pipeline**:

```
Raw HTML → Sanitize → Store in DB
         ↓
      Frontend retrieves → Display in reader
```

### 5.3 Example: Cleaned HTML Output

**Input**:

```html
<p>Here is <strong>bold</strong> text with a <a href="https://example.com" onclick="alert('hacked')">link</a>.</p>
<script>alert('XSS')</script>
<iframe src="https://evil.com"></iframe>
<style>body { display: none; }</style>
```

**Output**:

```html
<p>Here is <strong>bold</strong> text with a <a href="https://example.com">link</a>.</p>
```

---

## 6. Error Handling & Observability

### 6.1 Logging

All services log to stdout (structured JSON format):

```json
{
  "timestamp": "2024-11-25T10:30:00Z",
  "level": "ERROR",
  "service": "canonicalize_document",
  "job_id": "uuid",
  "error": "pdf_extraction_failed",
  "details": "..."
}
```

Aggregated via ELK / Datadog / CloudWatch.

### 6.2 Metrics

Key metrics tracked:

- **Ingestion**: Document count, avg extraction time, failure rate by error code
- **Embedding**: Chunk count, embedding latency, vector store health
- **Retrieval**: Query latency, cache hit rate, post-filter effectiveness
- **Chat**: Message count, context assembly time, LLM latency, token usage
- **Jobs**: Queue depth, job duration, retry count, DLQ size

### 6.3 Alerting

Alert thresholds (Phase 2):

- Vector store unavailable > 5 min
- DLQ size > 100
- P95 API latency > 2s
- Celery queue depth > 10,000

---

## 7. Scaling Considerations

### 7.1 Horizontal Scaling (Phase 2+)

- **API**: Auto-scale containers by CPU/memory
- **Celery**: Scale worker count based on queue depth
- **Postgres**: Read replicas for analytics/reporting

### 7.2 Vertical Scaling (Phase 1)

- **Start**: Single-instance Postgres, single Celery worker
- **Monitor**: CPU, memory, connection pool saturation
- **Upgrade path**: RDS larger instance, then read replicas

---

## 8. Technology Rationale Summary

| Choice | Alternative | Reason |
|--------|-------------|--------|
| Python/FastAPI | Node.js/Express | Rich document processing ecosystem (PyMuPDF, transformers), SQLAlchemy |
| PostgreSQL + SQLAlchemy 2.0 | MongoDB | ACID, full-text search, json support, pgvector, type safety |
| Alembic | Liquibase, Flyway | Tight SQLAlchemy integration, version control friendly |
| Celery | Bull/Node queues | Maturity, Python ecosystem fit, idempotency |
| React (web) | Vue, Svelte | Team familiarity, ecosystem maturity |
| pdf.js | pdfium, PDFSharp | Client-side rendering, JavaScript ecosystem |
| Clerk | Auth0, Supabase Auth | Simplicity, OIDC, no password handling burden |

