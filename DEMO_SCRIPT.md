# Nexus Demo Script

**walking through the system as if you were the data**

---

## 1. What Is Nexus?

- reading-first knowledge management system
- deterministic canonical text extraction (PDF/EPUB/HTML)
- persistent text anchoring (highlights survive re-ingestion)
- semantic search via pgvector embeddings
- (planned) LLM-augmented conversation

---

## 2. Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   Backend   │────▶│  PostgreSQL │
│  (Next.js)  │     │  (FastAPI)  │     │  + pgvector │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Celery    │
                    │  (Redis)    │
                    └─────────────┘
```

**tech stack:**
- backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic
- database: PostgreSQL 16 + pgvector (1536-dim embeddings)
- job queue: Redis + Celery
- frontend: Next.js 14, React 18, TanStack Query, Clerk auth
- embeddings: OpenAI `text-embedding-3-small`

---

## 3. Data Flow: Document Upload → Ready for Search

### 3.1 User Uploads a File

**frontend:**
- user selects file in upload UI
- `uploadDocument()` in `frontend/lib/api/documents.ts` calls `DocumentsService.uploadDocumentDocumentsPost()`
- sends multipart/form-data with `file`, `source_kind`, optional `title`

**API layer:**
- request hits `POST /documents` route in `backend/app/api/routes/documents.py::upload_document()`
- validates: file exists, size > 0, source_kind ∈ {pdf, epub, html}
- calls `StorageService().store_raw_blob(file)` → returns `blob_<uuid>` key
- calls `create_document_placeholder()` in `backend/app/services/documents.py`
  - creates Document row: status=`pending`, canonical_text=empty
  - returns Document ORM object
- `defer_task(session, ingest_document, str(doc.id))` queues Celery task
- commits transaction → triggers deferred task publish
- returns `DocumentUploadResponse` with `doc_<uuid>` typed ID

### 3.2 Celery: Ingest Document

**task entrypoint:**
- `backend/app/tasks/documents.py::ingest_document(document_id: str)`
- opens DB session, calls `run_ingest_document(session, document_id)`

**ingestion logic (`backend/app/services/ingestion.py::run_ingest_document`):**
- fetches Document row with `SELECT ... FOR UPDATE` (row lock)
- transitions status: `pending` → `processing`
- determines source_kind from MIME type
- calls `canonicalize_document(blob_key, source_kind)`

**canonicalization (`backend/app/services/ingestion.py::canonicalize_document`):**
- loads blob bytes from storage
- dispatches by source_kind:
  - **PDF**: `extract_pdf()` → PyMuPDF (fitz), page-by-page text extraction, tracks byte offsets per page
  - **EPUB**: `extract_epub()` → unzip, parse OPF/spine, lxml to extract text from XHTML files, track sections
  - **HTML**: `extract_html()` → Node.js subprocess runs `readability_helper.js` (Mozilla Readability)
- returns `CanonicalizationResult`:
  - `canonical_text`: deterministic UTF-8 string
  - `canonical_hash`: SHA256 of canonical_text
  - `content_hash`: SHA256 of original blob
  - `structure`: JSON (pages/sections with byte offsets)
  - `extractor_version`: e.g. "pdf-v1"

**back in `run_ingest_document`:**
- updates Document: `canonical_text`, `canonical_hash`, `content_hash`, `structure`, `text_byte_length`
- sets `anchored_content_hash` (for future highlight remapping)
- transitions status: `processing` → `ready`
- `defer_task(session, chunk_document, str(doc.id))` → queues chunking
- commits → fires deferred task

### 3.3 Celery: Chunk Document

**task entrypoint:**
- `backend/app/tasks/documents.py::chunk_document(document_id: str)`
- calls `run_chunk_document(session, doc_uuid)`

**chunking logic (`backend/app/services/chunking.py::run_chunk_document`):**
- guards: status must be `ready`, canonical_text must exist
- deletes any old chunks for this document
- calls `chunk_canonical_text(canonical_text)`

**chunking algorithm (`backend/app/services/chunking.py::chunk_canonical_text`):**
- splits on `\n\n+` (double newlines → paragraphs)
- greedily accumulates paragraphs until ~1000 chars
- each `ChunkSpan` stores: `start` (byte offset), `end`, `text`, `metadata`
- deterministic: same text → same chunks

**back in `run_chunk_document`:**
- creates `ContentChunk` rows for each span
- sets `doc.chunk_version = "doc_v1_chars_1000"`
- if chunks created > 0: `defer_task(session, embed_document, document_id)`
- commits → fires embedding task

### 3.4 Celery: Embed Document

**task entrypoint:**
- `backend/app/tasks/documents.py::embed_document(document_id: str)`
- calls `run_embed_document(session, doc_uuid)`

**embedding logic (`backend/app/services/embeddings.py::run_embed_document`):**
- guards: status=`ready`, chunk_version matches expected
- loads all ContentChunks for document
- partitions into already_embedded vs to_embed (idempotent)
- batch embeds via `embed_texts_with_default_client()` (batch size: 64)

**OpenAI call (`backend/app/services/openai_embeddings.py`):**
- `embed_texts_with_default_client(texts, model)` calls OpenAI Embeddings API
- model: `text-embedding-3-small`, 1536 dimensions
- returns list of float vectors

**back in `run_embed_document`:**
- stores embeddings on each chunk: `chunk.embedding = vector`, `chunk.embedding_model = model`
- sets `doc.embedding_status = "ready"`
- commits

**document is now ready for semantic search**

---

## 4. Data Flow: Semantic Search

### 4.1 User Submits Search Query

**frontend:**
- `searchChunks({ query, limit })` in `frontend/lib/api/search.ts`
- calls `SearchService.searchChunksSearchChunksPost()`

**API layer:**
- request hits `POST /search/chunks` in `backend/app/api/routes/search.py::search_chunks()`
- validates document_ids (if provided) are valid `doc_<uuid>` format
- calls `search_document_chunks_for_user(session, user, query, limit, document_ids)`

### 4.2 Search Execution

**search service (`backend/app/services/search.py::search_document_chunks_for_user`):**
- embeds query: `embed_texts_with_default_client([query], model)` → `query_vector`
- builds raw SQL with pgvector:
  ```sql
  SELECT cc.id, d.id, (1 - (cc.embedding <-> :query_vector)) as score, ...
  FROM content_chunks cc
  JOIN documents d ON d.id = cc.media_id
  WHERE d.user_id = :user_id   -- ACL: only user's documents
    AND d.embedding_status = 'ready'
    AND cc.embedding IS NOT NULL
  ORDER BY cc.embedding <-> :query_vector
  LIMIT :limit
  ```
- `<->` is pgvector's cosine distance operator
- score = 1 - distance (higher = more similar)

### 4.3 Results Returned

- maps rows to `SearchHit` dataclass: `chunk_id`, `document_id`, `score`, `text`, `text_start`, `text_end`
- API converts to `ChunkSearchHit` with typed IDs (`cnk_<uuid>`, `doc_<uuid>`)
- frontend receives results, renders in search UI

---

## 5. Data Flow: Document Retrieval

### 5.1 User Navigates to Document List

**frontend:**
- `useDocumentsList()` hook in `frontend/lib/hooks/useDocuments.ts`
- uses TanStack Query's `useInfiniteQuery`
- calls `fetchDocumentsList({ cursor, limit })` in `frontend/lib/api/documents.ts`
- which calls `DocumentsService.listDocumentsDocumentsGet()`

**API layer:**
- request hits `GET /documents` in `backend/app/api/routes/documents.py::list_documents()`
- auth: `rate_limit_authenticated` dependency extracts Bearer token, verifies JWT, syncs user
- calls `list_documents_for_user(session, user, pagination, status_filter)`

### 5.2 Document List Query

**service layer (`backend/app/services/documents.py::list_documents_for_user`):**
- base query: `Document.user_id == user.id`, `deleted_at IS NULL`
- applies status filter if provided
- cursor-based pagination: `ORDER BY created_at DESC, id DESC`
- fetches `limit + 1` rows to determine `has_more`
- encodes next cursor: `base64({"created_at": ..., "id": ...})`

### 5.3 Document Detail

**frontend:**
- `useDocumentDetail(documentId)` hook
- calls `fetchDocument(documentId)` → `DocumentsService.getDocumentDocumentsDocumentIdGet()`

**API layer:**
- `GET /documents/{document_id}` → `get_document()` route
- parses typed ID via `from_api_id(document_id)` → extracts UUID
- calls `get_document_for_user(session, user, doc_uuid)`
- service enforces: exists + owned by user + not deleted
- returns 404 if any check fails (no existence leak)

---

## 6. Data Flow: Highlight Creation

### 6.1 User Selects Text

**frontend (`frontend/components/reader/HtmlHighlightReader.tsx`):**
- `handleMouseUp()` triggered on text selection
- gets `window.getSelection()`, validates it's within reader container
- calls `resolveSelectionToCanonicalOffsets()` from `frontend/lib/anchoring/core.ts`
  - maps browser selection to character offsets in canonical_text
- sets `pendingSelection` state: `{ textStart, textEnd, quote }`

### 6.2 User Clicks "Add Highlight"

**frontend:**
- `handleCreateHighlight()` calls `createHighlight()` from `useCreateHighlight` hook
- which calls `createHighlightApi()` in `frontend/lib/api/highlights.ts`
- sends `POST /highlights` with: `media_type`, `media_id`, `anchor_type`, `text_start`, `text_end`

**API layer:**
- `POST /highlights` → `backend/app/api/routes/highlights.py::create_highlight_endpoint()`
- validates: media_type=document, anchor_type ∈ {text, pdf}
- parses media_id, verifies document exists and user owns it
- for text anchors: extracts quote/prefix/suffix from canonical_text
- calls `create_highlight()` in `backend/app/services/highlights.py`

### 6.3 Anchor Validation

**service layer (`backend/app/services/highlights.py::create_highlight`):**
- verifies user owns the document
- for text anchors, calls `_validate_text_anchor()`:
  - checks `text_start < text_end`, both within bounds
  - verifies `canonical_text[text_start:text_end] == quote`
  - verifies prefix/suffix match surrounding context
- creates `Highlight` row with validated offsets

### 6.4 Highlight Persisted

- highlight stored with: `user_id`, `media_type=document`, `media_id`, `anchor_type=text`
- `text_start`, `text_end` are character offsets (codepoint indices, not bytes)
- `quote`, `prefix`, `suffix` stored for future remapping
- returns `HighlightSummary` → API converts to typed IDs → frontend receives

---

## 7. Data Flow: Annotation Creation

### 7.1 User Adds Note to Highlight

**frontend:**
- annotation UI calls `createAnnotationApi()` in `frontend/lib/api/annotations.ts`
- sends `POST /annotations` with: `highlight_id`, `content`

**API layer:**
- `POST /annotations` → `backend/app/api/routes/annotations.py::create_annotation_endpoint()`
- parses highlight_id, calls `create_annotation()` in service

**service layer (`backend/app/services/highlights.py::create_annotation`):**
- validates content non-empty
- verifies highlight exists and user owns it
- creates `Annotation` row: `user_id`, `highlight_id`, `content`
- returns `AnnotationSummary`

---

## 8. Data Flow: Reading Position

### 8.1 User Opens Document

**frontend:**
- creates/gets reader session via `POST /readers` with `document_id`

**API layer:**
- `backend/app/api/routes/readers.py::create_reader()`
- calls `get_or_create_reader_for_user()` in `backend/app/services/readers.py`
- idempotent: one reader per (user, document) pair

### 8.2 User Scrolls

**frontend:**
- periodically calls `PATCH /readers/{reader_id}` with `current_position`

**service layer (`backend/app/services/readers.py::update_reader_position`):**
- updates `reader.current_position` and `reader.last_read_at`
- position is byte offset in canonical_text

---

## 9. Authentication Flow

### 9.1 Every Authenticated Request

**middleware chain:**
1. CORS middleware (FastAPI)
2. trace_id middleware → generates `req_<uuid>`, attaches to request.state
3. logging middleware → logs request with trace_id
4. security headers middleware → adds `X-Content-Type-Options`, etc.

**auth dependency (`backend/app/core/auth/deps.py::get_current_user`):**
- extracts Bearer token from `Authorization` header
- calls `verify_clerk_jwt(token)` in `backend/app/core/auth/jwt.py`
  - fetches Clerk JWKS (cached)
  - verifies JWT signature, expiry, issuer, audience
  - returns decoded claims
- queries `User` by `external_user_id` (Clerk's `sub` claim)
- if not found: creates new User row (first-time login)
- attaches `user_id` to request.state for logging

---

## 10. Error Handling

**all errors return standardized envelope:**
```json
{
  "ok": false,
  "error": {
    "code": "resource/not_found",
    "message": "Document not found",
    "details": { "resource_type": "document" },
    "trace_id": "req_abc123..."
  }
}
```

**error codes:**
- `auth/unauthorized`, `auth/token_expired`
- `resource/not_found`, `resource/conflict`
- `validation/invalid_field`, `validation/required_field`
- `ratelimit/exceeded`
- `server/internal_error`
- `service/unavailable`, `service/timeout`

---

## 11. Key Typed IDs

| Entity | Prefix | Example |
|--------|--------|---------|
| User | `usr_` | `usr_11111111-2222-3333-4444-555555555555` |
| Document | `doc_` | `doc_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` |
| Chunk | `cnk_` | `cnk_xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| Highlight | `hl_` | `hl_yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy` |
| Annotation | `ann_` | `ann_zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz` |
| Conversation | `conv_` | `conv_...` |
| Message | `msg_` | `msg_...` |
| Reader | `rdr_` | `rdr_...` |

- conversion: `to_api_id("document", uuid)` → `doc_<uuid>`
- parsing: `from_api_id("doc_abc...")` → `("document", UUID("abc..."))`

---

## 12. Database Models Summary

| Model | Key Fields |
|-------|------------|
| `User` | `external_user_id` (Clerk sub), `email` |
| `Document` | `user_id`, `canonical_text`, `canonical_hash`, `status`, `embedding_status` |
| `ContentChunk` | `media_type`, `media_id`, `text`, `text_start`, `text_end`, `embedding` (1536-dim) |
| `Highlight` | `user_id`, `media_id`, `text_start`, `text_end`, `quote`, `prefix`, `suffix` |
| `Annotation` | `user_id`, `highlight_id`, `content` |
| `Reader` | `user_id`, `document_id`, `current_position`, `last_read_at` |
| `Conversation` | `user_id`, `title`, `last_message_at` |
| `Message` | `conversation_id`, `role`, `content` |

---

## 13. Future (Not Yet Implemented)

- **LLM integration**: RAG pipeline, chat completion
- **Chat UI**: message interface with citations
- **Highlight remapping**: when canonical_text changes, remap highlights via exact/fuzzy match
- **Document linking**: bidirectional references between documents
- **BM25 hybrid search**: combine keyword + vector search

---

## 14. Demo Talking Points

**"let me walk you through what happens when you upload a document..."**

1. file hits backend, stored via content-addressable storage
2. creates pending document row, queues Celery task
3. ingestion extracts deterministic canonical text (same file → same text always)
4. chunking splits into ~1000 char paragraphs with byte offsets
5. embedding generates 1536-dim vectors via OpenAI
6. search uses pgvector cosine similarity, respects user ACL
7. highlights anchor to canonical text via character offsets
8. all IDs are typed (doc_, hl_, etc.) for API clarity

**"what makes this interesting..."**

- **deterministic extraction**: re-ingesting same file produces identical canonical_text
- **anchor stability**: highlights store quote/prefix/suffix for future remapping
- **offset semantics**: character offsets (codepoints), not bytes - frontend/backend aligned
- **ACL at query boundary**: users only see their own docs, no existence leaks

---

*end of demo script*

