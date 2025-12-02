# Nexus Codebase Survey

**Generated**: December 2, 2025  
**Version**: Phase 1 (in progress)

---

## 1. Executive Summary

Nexus is a **reading-first knowledge management system** that provides:
- Deterministic canonical text extraction from documents (PDF, EPUB, HTML)
- Persistent text anchoring (highlights survive document re-ingestion)
- Semantic search via pgvector embeddings
- LLM-augmented conversation (planned, not yet implemented)

### Current Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Document ingestion | ✅ Complete | PDF (PyMuPDF), EPUB (lxml), HTML (Mozilla Readability) |
| Chunking pipeline | ✅ Complete | Paragraph-aware, ~1000 char chunks, byte offsets |
| Embeddings | ✅ Complete | OpenAI `text-embedding-3-small`, pgvector storage |
| Semantic search | ✅ Complete | Vector similarity with ACL enforcement |
| Highlights | ✅ Backend complete | Anchor validation, byte-range storage |
| Annotations | ✅ Backend complete | Attached to highlights, soft-delete |
| Conversations | ✅ Backend complete | Thread management, message storage |
| Readers | ✅ Backend complete | Reading position tracking |
| Document list UI | ✅ Complete | Infinite scroll, status badges |
| Document detail UI | ✅ Partial | Shows metadata, no reader view |
| LLM integration | 🚧 Not started | RAG pipeline, chat completion |
| Chat UI | 🚧 Not started | Message interface, citations |
| Document upload UI | 🚧 Not started | File picker, progress |
| Highlight creation UI | 🚧 Not started | Text selection, annotation panel |

---

## 2. Architecture Overview

### 2.1 Technology Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 + pgvector extension |
| Job Queue | Redis + Celery |
| Frontend | Next.js 14, React 18, TypeScript, TanStack Query |
| Auth | Clerk (OIDC, JWTs) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dimensions) |

### 2.2 Directory Structure

```
nexus/
├── backend/
│   ├── app/
│   │   ├── api/routes/       # FastAPI route handlers (10 files)
│   │   ├── core/             # Config, auth, errors, middleware
│   │   ├── db/               # Database session management
│   │   ├── models/           # SQLAlchemy ORM models (11 models)
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic layer (10 services)
│   │   └── tasks/            # Celery async tasks
│   ├── alembic/              # Database migrations (5 migrations)
│   └── tests/                # pytest test suite (30+ test files)
├── frontend/
│   ├── app/                  # Next.js App Router
│   │   ├── (auth)/           # Public auth routes (sign-in, sign-up)
│   │   └── (protected)/      # Authenticated routes (documents)
│   └── lib/
│       ├── api/              # API client wrappers
│       └── generated-api/    # OpenAPI-generated TypeScript client
├── infra/
│   └── docker-compose.yml    # Local dev infrastructure
└── spec/                     # Design specifications
```

---

## 3. Data Models (SQLAlchemy ORM)

### 3.1 Core Entities

#### User
```python
# app/models/user.py
- id: UUID (primary key)
- external_user_id: str (Clerk 'sub' claim, unique)
- email: str (unique)
- created_at, updated_at: datetime
```
**Relationships**: documents, highlights, annotations, conversations, messages, libraries, readers

#### Document
```python
# app/models/document.py
- id: UUID (primary key)
- user_id: UUID (FK → users.id, owner)
- title: str (512 chars)
- author, published_date, source_url: optional metadata

# Original blob storage
- original_blob_key: str (storage key)
- original_mime_type: str (application/pdf, etc.)
- original_size_bytes: int

# Canonical text (immutable after extraction)
- canonical_text: str (full text)
- canonical_hash: str (SHA256 of canonical_text)
- content_hash: str (SHA256 of original blob)
- anchored_content_hash: str (hash at highlight creation, triggers remap)
- text_byte_length: int
- extractor_version: str (pdf-v1, epub-v1, html-v1)

# Processing status
- status: enum('pending', 'processing', 'ready', 'failed')
- embedding_status: enum('pending', 'ready', 'failed')
- error_code, error_message: optional error details

# Timestamps and soft-delete
- deleted_at, created_at, updated_at: datetime
```

#### ContentChunk
```python
# app/models/chunk.py
- id: UUID (primary key)
- media_type: enum('document', 'episode', 'video')
- media_id: UUID (polymorphic FK)
- chunk_version: str (e.g., "doc_v1_chars_1000")
- embedding_model: str (e.g., "text-embedding-3-small")
- text_start, text_end: int (byte offsets)
- text: str (chunk content)
- embedding: Vector(1536) (pgvector)
- chunk_metadata: JSONB
- created_at: datetime
```

#### Highlight
```python
# app/models/highlight.py
- id: UUID (primary key)
- user_id: UUID (FK → users.id)
- media_type: enum('document', 'episode', 'video')
- media_id: UUID (polymorphic FK)
- anchor_type: enum('text', 'pdf', 'transcript')

# Anchoring (byte offsets into canonical text)
- text_start, text_end: int
- quote: str (exact highlighted text)
- prefix, suffix: str (up to 64 bytes context)

# PDF-specific
- pdf_page_number, pdf_char_offset: int
- pdf_file_hash: str (SHA256)
- pdf_extraction_confidence: float

# Transcript-specific
- time_start, time_end: float (seconds)
- transcript_hash: str

# Mutable fields
- color: enum('yellow', 'blue', 'green', 'pink', 'purple')
- is_hidden, is_detached, is_public: bool
- detached_reason: str

# Lifecycle
- deleted_at, created_at, updated_at: datetime
```

#### Annotation
```python
# app/models/annotation.py
- id: UUID (primary key)
- user_id: UUID (FK → users.id)
- highlight_id: UUID (FK → highlights.id, required)
- content: str (note text)
- is_public: bool
- deleted_at, created_at, updated_at: datetime
```

#### Conversation
```python
# app/models/conversation.py
- id: UUID (primary key)
- user_id: UUID (FK → users.id)
- title: str (optional)
- description: str (optional)
- last_message_at: datetime
- summary_state: JSONB (future)
- is_public: bool
- deleted_at, created_at, updated_at: datetime
```

#### Message
```python
# app/models/message.py
- id: UUID (primary key)
- conversation_id: UUID (FK → conversations.id)
- user_id: UUID (FK → users.id)
- role: enum('user', 'assistant')
- content: str
- effective_model_id: str (for assistant messages)
- token_count: int
- is_public: bool
- deleted_at, created_at, updated_at: datetime
```

#### Reader
```python
# app/models/reader.py
- id: UUID (primary key)
- user_id: UUID (FK → users.id)
- document_id: UUID (FK → documents.id)
- current_position: int (byte offset, nullable)
- last_read_at: datetime
- created_at, updated_at: datetime

# Unique constraint: (user_id, document_id)
```

#### Link
```python
# app/models/link.py
- id: UUID (primary key)
- source_type, target_type: enum('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')
- source_id, target_id: UUID
- created_by_user_id: UUID (FK → users.id)
- created_at: datetime

# Constraint: source != target (no self-links)
# Unique: (source_type, source_id, target_type, target_id)
```

#### Library (for sharing)
```python
# app/models/library.py
- Library: id, user_id, name, description, is_public
- LibraryMembership: library_id, user_id, role (owner/editor/viewer)
- LibraryMedia: library_id, media_type, media_id
- ObjectLibraryVisibility: object_type, object_id, library_id
```

### 3.2 Three Embedding Spaces

The system supports three types of chunks for different search semantics:

| Chunk Type | Sources | Purpose |
|------------|---------|---------|
| ContentChunk | Documents, episodes, videos | Primary content search |
| ThoughtChunk | Annotations, messages, conversation summaries | User's own thoughts |
| MetadataChunk | Titles, authors, descriptions | Metadata/title search |

**Only ContentChunk is implemented in Phase 1.**

---

## 4. API Endpoints

### 4.1 Authentication
All endpoints (except `/health`) require Clerk JWT via `Authorization: Bearer <token>`.

### 4.2 Document Endpoints (`/documents`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| POST | `/documents` | Upload document (multipart) | ✅ |
| GET | `/documents` | List user's documents (paginated) | ✅ |
| GET | `/documents/{id}` | Get document detail | ✅ |
| GET | `/documents/{id}/readers` | List readers for document | ✅ |

**Upload Request** (multipart/form-data):
- `file`: UploadFile (required)
- `source_kind`: "pdf" | "epub" | "html" (required)
- `title`: string (optional)

**Response envelope**: `{ "data": {...} }` with typed IDs (`doc_<uuid>`)

### 4.3 Highlight Endpoints (`/highlights`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| POST | `/highlights` | Create highlight with anchor | ✅ |
| GET | `/highlights/{id}` | Get highlight by ID | ✅ |
| DELETE | `/highlights/{id}` | Soft-delete highlight | ✅ |
| GET | `/highlights` | List user's highlights | ✅ |

**Create Request**:
- `document_id`: typed ID
- `text_start`, `text_end`: byte offsets
- `quote`, `prefix`, `suffix`: anchor context
- `anchor_type`: "text" | "pdf" | "transcript"

### 4.4 Annotation Endpoints (`/annotations`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| POST | `/annotations` | Create annotation on highlight | ✅ |
| GET | `/annotations/{id}` | Get annotation by ID | ✅ |
| PATCH | `/annotations/{id}` | Update annotation content | ✅ |
| DELETE | `/annotations/{id}` | Soft-delete annotation | ✅ |
| GET | `/annotations` | List user's annotations | ✅ |
| GET | `/highlights/{id}/annotations` | List annotations on highlight | ✅ |

### 4.5 Conversation Endpoints (`/conversations`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| POST | `/conversations` | Create conversation | ✅ |
| GET | `/conversations` | List user's conversations | ✅ |
| GET | `/conversations/{id}` | Get conversation by ID | ✅ |
| POST | `/conversations/{id}/messages` | Append user message | ✅ |
| GET | `/conversations/{id}/messages` | List messages (paginated) | ✅ |

**Note**: Assistant messages are not yet implemented (requires LLM integration).

### 4.6 Reader Endpoints (`/readers`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| POST | `/readers` | Create/get reader for document | ✅ |
| GET | `/readers/{id}` | Get reader by ID | ✅ |
| PATCH | `/readers/{id}` | Update reading position | ✅ |

### 4.7 Search Endpoint (`/search`)

| Method | Endpoint | Description | Status |
|--------|----------|-------------|--------|
| POST | `/search` | Semantic search over documents | ✅ |

**Request**:
- `query`: search text
- `limit`: max results (default 20, max 100)
- `document_ids`: optional list to restrict search

**Response**: List of `SearchHit` with chunk_id, document_id, score, text, offsets

### 4.8 Typed IDs

All API IDs use prefixed format:
- `doc_<uuid>` - documents
- `hl_<uuid>` - highlights
- `ann_<uuid>` - annotations
- `conv_<uuid>` - conversations
- `msg_<uuid>` - messages
- `rdr_<uuid>` - readers
- `lib_<uuid>` - libraries
- `link_<uuid>` - links

---

## 5. Backend Services

### 5.1 Ingestion Pipeline (`services/ingestion.py`)

**Flow**: Upload → Store blob → Create placeholder → Celery task → Canonicalize → Chunk → Embed

```
canonicalize_document(blob_key, source_kind)
├── extract_pdf(blob_bytes)      # PyMuPDF (fitz)
├── extract_epub(blob_bytes)     # zipfile + lxml
└── extract_html(blob_bytes)     # Node.js readability_helper.js

Returns: CanonicalizationResult
├── canonical_text: str
├── canonical_hash: SHA256
├── content_hash: SHA256 (original blob)
├── structure: JSON (pages/sections)
├── extractor_version: str
└── text_byte_length: int
```

### 5.2 Chunking (`services/chunking.py`)

**Algorithm**: Paragraph-aware greedy chunking
- Split on `\n\n+` (double newlines)
- Accumulate paragraphs until ~1000 chars
- Track byte offsets into canonical text
- Version: `doc_v1_chars_1000`

```python
chunk_canonical_text(canonical_text) → list[ChunkSpan]
# ChunkSpan: start, end (byte offsets), text, metadata

run_chunk_document(session, document_id) → int
# Returns number of chunks created
```

### 5.3 Embeddings (`services/embeddings.py`)

**Model**: OpenAI `text-embedding-3-small` (1536 dimensions)

```python
run_embed_document(session, document_id) → EmbeddingResult
# Embeds all content chunks for a document
# Idempotent: skips already-embedded chunks
# Batch size: 64 chunks per API call
```

### 5.4 Search (`services/search.py`)

**Algorithm**: Vector similarity via pgvector

```python
search_document_chunks_for_user(session, user, query, limit, document_ids)
# 1. Embed query using same model
# 2. pgvector cosine distance search
# 3. Filter by user's documents (ACL)
# Returns: list[SearchHit]
```

### 5.5 Highlights (`services/highlights.py`)

**Anchor validation**:
- Text anchors: Verify quote/prefix/suffix match canonical_text at byte offsets
- PDF anchors: Verify page_number, char_offset, file_hash exist
- Transcript anchors: Verify time_start/time_end (future)

### 5.6 Storage (`services/storage.py`)

**Features**:
- Local filesystem storage (configurable path)
- Streaming writes (64KB chunks)
- Maximum size enforcement (250MB default)
- Atomic writes (temp file → rename)
- Returns `blob_<uuid>` keys

---

## 6. Celery Tasks

### 6.1 Task Definitions (`tasks/documents.py`)

| Task | Queue | Purpose | Retry |
|------|-------|---------|-------|
| `ingest_document` | documents | Canonicalize uploaded document | 3x with backoff |
| `chunk_document` | documents | Split canonical text into chunks | 3x with backoff |
| `embed_document` | embeddings | Generate vector embeddings | 3x with backoff |
| `remap_highlights_for_document` | documents | **STUB** - Remap highlights on hash change | - |

### 6.2 Pipeline Flow

```
upload_document (API)
    └── ingest_document.delay()
            └── run_ingest_document()
                    ├── canonicalize_document()
                    ├── Update document: canonical_text, status='ready'
                    └── chunk_document.delay()
                            └── run_chunk_document()
                                    ├── Delete old chunks
                                    ├── chunk_canonical_text()
                                    ├── Insert ContentChunk rows
                                    └── embed_document.delay()
                                            └── run_embed_document()
                                                    ├── embed_texts_with_default_client()
                                                    └── Update embedding, embedding_status='ready'
```

---

## 7. Frontend

### 7.1 Pages

| Route | Component | Description | Status |
|-------|-----------|-------------|--------|
| `/` | `page.tsx` | Redirects to `/app` | ✅ |
| `/auth/sign-in` | Clerk | Sign-in page | ✅ |
| `/auth/sign-up` | Clerk | Sign-up page | ✅ |
| `/app` | `(protected)/page.tsx` | Welcome page | ✅ |
| `/app/documents` | `documents/page.tsx` | Document list | ✅ |
| `/app/documents/[id]` | `[documentId]/page.tsx` | Document detail | ✅ (partial) |

### 7.2 Protected Layout

The `(protected)/layout.tsx` provides:
- Clerk authentication wrapper
- TanStack Query provider
- OpenAPI client configuration
- Navigation header with UserButton

### 7.3 API Client

**Configuration** (`lib/api/client.ts`):
- Uses Clerk's `getToken()` for Bearer auth
- Base URL from `NEXT_PUBLIC_API_URL` env var
- OpenAPI-generated TypeScript client

### 7.4 Document List Page

**Features**:
- Infinite scroll pagination
- Status badges (pending/processing/ready/failed)
- Loading spinner
- Error state with retry
- Empty state message
- Click to navigate to detail

### 7.5 Document Detail Page

**Features**:
- Back navigation
- Full metadata display
- Status badge
- Processing/failed status messages
- **Missing**: Reader view, canonical text display, highlight creation

---

## 8. Infrastructure

### 8.1 Docker Compose

```yaml
services:
  db:           # PostgreSQL 16 + pgvector
  test-db:      # Separate test database
  redis:        # Celery broker + result backend
  worker:       # Celery worker (documents + embeddings queues)
```

### 8.2 Environment Variables

```bash
# Database
DATABASE_URL=postgresql+psycopg://app_user:password@localhost:5432/nexus

# Redis
REDIS_URL=redis://localhost:6379/0

# Clerk Auth
CLERK_JWKS_URL=https://[instance].clerk.accounts.com/.well-known/jwks.json
CLERK_ISSUER=https://[instance].clerk.accounts.com
CLERK_AUDIENCE=[api-audience]

# OpenAI
OPENAI_API_KEY=sk-...

# Storage
STORAGE_PATH=./storage/documents
MAX_BLOB_SIZE_BYTES=262144000  # 250MB
```

---

## 9. What Users Can Currently Do

### 9.1 Implemented User Flows

1. **Sign in/up via Clerk** → Redirects to app home

2. **View document list**:
   - See all uploaded documents
   - Filter by status (pending/processing/ready/failed)
   - Infinite scroll pagination
   - Click to view detail

3. **View document detail**:
   - See metadata (title, type, status, dates)
   - See processing status messages

4. **Upload documents** (via API only, no UI):
   - POST multipart to `/documents`
   - PDF, EPUB, HTML supported
   - Automatic ingestion pipeline triggered

5. **Create highlights** (via API only):
   - POST to `/highlights` with anchor data
   - Anchor validation against canonical text

6. **Create annotations** (via API only):
   - POST to `/annotations` with highlight_id
   - Update/delete annotations

7. **Search documents** (via API only):
   - Semantic search over embedded content
   - Results include chunk text and byte offsets

8. **Track reading position** (via API only):
   - Create/update reader for document
   - Stores current byte offset

### 9.2 What Users CANNOT Do Yet

1. **Upload documents via UI** - No file picker component

2. **View document content** - No reader/viewer component

3. **Create highlights via UI** - No text selection handling

4. **See highlights in reader** - No highlight rendering

5. **Add annotations via UI** - No annotation panel

6. **Chat with documents** - LLM integration not implemented

7. **See search results** - No search UI

8. **Link documents** - Links model exists but no UI/endpoints fully wired

---

## 10. What Remains To Be Done

### 10.1 Backend (remaining from PR Roadmap)

| PR | Description | Status |
|----|-------------|--------|
| 7.2 | LLM Integration + Prompt Assembly | Not started |
| 7.3 | RAG Pipeline + Context Injection | Not started |
| 8.1 | Document Linking endpoints | Partial (model exists) |
| 8.2 | Test Coverage + Production Hardening | In progress |

### 10.2 Frontend (not started)

| Feature | Description |
|---------|-------------|
| Document upload UI | File picker, progress, validation |
| Document reader | PDF.js for PDFs, HTML rendering for EPUB/web |
| Text selection | Selection API for highlight creation |
| Highlight rendering | DOM overlay for highlights |
| Annotation panel | Right-side panel for notes |
| Chat interface | Message input, response display, citations |
| Search UI | Search input, results display |

### 10.3 Highlight Remapping

The `remap_highlights_for_document` task is a **stub**. Full implementation needs:
- Exact match search in new canonical text
- Fuzzy search with ≤10% edit distance
- Update highlight offsets or mark as detached

### 10.4 Production Hardening

| Area | Status |
|------|--------|
| Rate limiting | ✅ Implemented |
| CORS | ✅ Configured |
| Security headers | ✅ Implemented |
| Error envelopes | ✅ Implemented |
| Pagination | ✅ Cursor-based |
| Test coverage | ~70% (needs more) |
| Logging | ✅ Structured JSON |
| Monitoring | Not configured |
| CI/CD | Not configured |

---

## 11. Test Coverage

### 11.1 Backend Tests

```
tests/
├── api/                          # API integration tests
│   ├── test_annotations_api.py
│   ├── test_conversations_api.py
│   ├── test_documents_*.py       # upload, list, detail
│   ├── test_highlights_api.py
│   ├── test_readers_api.py
│   └── test_search_api.py
├── test_canonicalization_*.py    # PDF, EPUB, HTML extraction
├── test_chunking_*.py            # Algorithm and service
├── test_embeddings_*.py          # Schema and service
├── test_*_service.py             # Service layer tests
├── test_auth.py
├── test_cors.py
├── test_rate_limit.py
├── test_security_headers.py
└── conftest.py                   # pytest fixtures
```

### 11.2 Frontend Tests

```
frontend/app/__tests__/
frontend/app/(protected)/documents/__tests__/
├── detail.test.tsx
└── page.test.tsx
```

---

## 12. Key Design Decisions

### 12.1 Canonical Text Over Native Formats
- All documents converted to deterministic UTF-8 text
- Highlights anchor to byte offsets in canonical text
- Enables consistent search and anchoring across formats

### 12.2 Hash-Based Versioning
- `content_hash`: SHA256 of original blob
- `canonical_hash`: SHA256 of canonical text
- `anchored_content_hash`: Hash at highlight creation time
- Triggers remap when hashes change

### 12.3 Typed IDs at API Boundary
- Internal: raw UUIDs in database
- External: prefixed strings (`doc_`, `hl_`, etc.)
- Conversion at API layer via `to_api_id()` / `from_api_id()`

### 12.4 Celery for Background Jobs
- Named queues: `documents`, `embeddings`
- Retry with exponential backoff
- Transaction-per-task pattern

### 12.5 ACL via User Ownership
- All resources have `user_id` foreign key
- Query filters enforce ownership
- Unknown/forbidden resources return 404 (no existence leak)

---

## 13. Appendix: File Reference

### Backend
- `app/main.py` - FastAPI app factory
- `app/core/config.py` - Settings from env vars
- `app/core/auth/` - Clerk JWT verification
- `app/core/errors.py` - Error codes and exceptions
- `app/core/ids.py` - Typed ID conversion
- `app/core/pagination.py` - Cursor encoding/decoding
- `app/db/session.py` - SQLAlchemy session management
- `app/celery_app.py` - Celery configuration

### Frontend
- `app/layout.tsx` - Root layout with ClerkProvider
- `app/(protected)/layout.tsx` - Auth-protected layout
- `lib/api/client.ts` - OpenAPI client configuration
- `lib/generated-api/` - Auto-generated TypeScript client

### Infrastructure
- `infra/docker-compose.yml` - Local development services
- `backend/Makefile` - Build/test commands
- `frontend/Makefile` - Build/test commands

---

*End of Codebase Survey*

