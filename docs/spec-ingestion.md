# Nexus Subsystem Spec: Ingestion & Media

## 1. Scope

This subsystem handles all media ingestion, processing, storage, and lifecycle management for Nexus. It is responsible for accepting URLs and file uploads, deduplicating content, extracting text and generating canonical representations, managing processing state transitions, orchestrating chunking and embedding jobs, and providing media metadata retrieval.

**In scope:**
- URL and file upload entrypoints (HTTP/HTTPS URLs, EPUB files, PDF files)
- Content-based deduplication with canonical URL hint
- Media record creation and initial library insertion (default library auto-add)
- Extraction pipeline: URL fetch, file parsing, text extraction
- Canonical text generation: `plain_text` (deterministic, immutable after completion)
- Display HTML generation: `html` (for HTML/EPUB media)
- Processing status state machine: `pending` → `processing` → `ready_for_reading` → `indexed` → `failed`
- Chunking job orchestration (single strategy in v1; multi-strategy support deferred to v2)
- Embedding generation job orchestration
- Retry semantics (state reset, chunk/embedding wipe)
- Idempotency guarantees for job execution
- Media listing with pagination
- Failure reporting (`failure_reason` field population)
- Format validation and size limits
- Observability (structured logs, processing metrics)

**Explicitly out of scope (non-goals):**
- Library permission decisions beyond auto-add to default library
- Library membership management (adding/removing users, role changes)
- Social object behavior (highlights, annotations, conversations)
- Search functionality (this subsystem only sets prerequisites: `indexed` status)
- LLM calls for metadata repair, summarization, or enrichment
- Visibility rule enforcement (media is globally readable)
- Deduplication UI prompts or user confirmation flows
- Author normalization, disambiguation, or external lookups (ingestion uses simple exact-match extraction only)
- Content recommendation or discovery algorithms
- Chunking strategy selection (configured externally)
- Embedding model selection (configured externally)
- Text extraction algorithm selection (configured externally)

## 2. Dependencies

**External services:**
- PostgreSQL database (Media, Chunk, LibraryMedia tables)
- Object storage (Supabase Storage or S3-compatible) for uploaded file persistence (`storage_path` is opaque string owned by storage layer)
- Celery task queue for asynchronous job execution
- Redis for Celery broker and result backend
- HTTP client for URL fetching (timeout: 10s, max redirects: 5)
- Text extraction interface (implementation-agnostic; must be deterministic; requires separate alignment spec - see §11)
- Chunking interface (implementation-agnostic; strategies configured externally)
- Embedding API interface (implementation-agnostic; dimension count configured externally)
- pgvector extension for embedding storage and ANN indexing

**CRITICAL ARCHITECTURAL WARNING:**
This spec assumes media is globally readable by all authenticated users (v1 product decision). This is a significant architectural choice with the following consequences:
- Users cannot have truly private documents in v1
- Deduplication is global (duplicate content is never stored twice, even across users)
- Privacy exists only at the social layer (highlights, annotations, conversations)
- Future private media support will require major rearchitecture (per-media visibility flags, deduplication rework, access control layer)
- This decision prioritizes simplicity and storage efficiency over user privacy expectations

**Internal subsystems:**
- Authentication subsystem (for `uploader_user_id` tracking)
- Library subsystem (for default library lookup and `LibraryMedia` row creation)
- Subscription subsystem (for tier limit enforcement: free tier = 5 media max in default library)

**Database schema dependencies and write permissions:**

The following table clarifies who can write to what, preventing future subsystems from "helpfully" modifying ingestion-owned data.

| Table | Who Can Write | Notes |
|-------|---------------|-------|
| `media` | Ingestion subsystem only | No direct writes from other subsystems; all media creation goes through ingestion |
| `chunk` | Ingestion subsystem only | Only via chunking/embedding tasks; no manual chunk creation |
| `author` | Ingestion subsystem + Metadata subsystem (future) + User-initiated creation (v1) | Ingestion: insert-only during extraction. Users: create-only (no edit/delete in v1). Metadata subsystem (future): comprehensive management |
| `media_author` | Ingestion subsystem + Metadata subsystem (future) + User-initiated creation (v1) | Same write rules as `author` table |
| `library_media` | Ingestion subsystem + Library subsystem | Ingestion: inserts default library rows only. Library subsystem: owns full lifecycle (add/remove media from libraries) |

**Critical constraints:**
- Ingestion MUST NEVER update or delete existing `author` or `media_author` rows (insert-only)
- Other subsystems MUST NOT write to `media` or `chunk` tables directly
- Library subsystem owns `library_media` lifecycle; ingestion only inserts default library associations

**CRITICAL CLARIFICATION: Author Subsystem Ownership**

This spec expands ingestion scope to include author creation and association logic. This is an explicit design decision with the following consequences:

**What ingestion owns (v1):**
- Creating `author` rows during extraction (exact string match, no normalization beyond whitespace)
- Creating `media_author` associations
- Splitting author strings on separators (comma, " and ", " & ")
- Best-effort extraction from document metadata only (HTML `<meta>`, EPUB `<dc:creator>`)

**What ingestion does NOT own:**
- Author normalization ("John Smith" vs "J. Smith" are distinct authors in v1)
- Author disambiguation (external lookups, LLM-based merging)
- User-facing author editing/deletion (only creation allowed in v1)
- Author quality cleanup (metadata subsystem responsibility in future versions)

**Consequence:** This will create a messy author table with low-quality names ("NYTimes Staff", "–", "Unknown") and naive splitting artifacts. This is accepted technical debt; cleanup is deferred to a future metadata subsystem.

**Shared write access:**
The `author` and `media_author` tables have shared write access:
- Ingestion subsystem: creates authors automatically during extraction (insert-only, never updates/deletes)
- User-initiated metadata entry: users may manually create authors via UI (v1: create-only, no edit/delete)
- Future metadata subsystem: will define comprehensive author management (editing, merging, disambiguation)

## 3. Responsibilities

This subsystem MUST:

1. Accept media upload requests via URL or file upload
2. Validate media kind (`html`, `epub`, `pdf` only in v1)
3. Enforce maximum file size limits (configured per kind; v1 defaults: PDF=50MB, EPUB=25MB, HTML=10MB)
4. Perform content-based deduplication (SHA-256 hash + canonical URL hint)
5. Create `Media` row with `processing_status = 'pending'` if new content
6. Insert `LibraryMedia` row linking media to user's default library (idempotent)
7. Trigger asynchronous extraction job with exclusive lock on media row
8. Extract canonical `plain_text` using deterministic text extraction interface
9. Generate display `html` for HTML/EPUB media (sanitized, reading-order preserved)
10. Transition `processing_status` atomically: `pending` → `processing` → `ready_for_reading`
11. Trigger asynchronous chunking job after reaching `ready_for_reading`
12. Chunk `plain_text` using the configured chunking strategy
13. Trigger asynchronous embedding job after chunking completes
14. Generate embeddings for all chunks via embedding API interface
15. Transition `processing_status` to `indexed` after chunking and embedding complete
16. Transition to `failed` on any processing error, populate `failure_reason` enum
17. Support retry with row-level lock: reset to `pending`, delete all chunks, re-enqueue
18. Provide read endpoints for media retrieval (by ID, list with cursor-based pagination)
19. Provide status polling endpoint for client progress tracking
20. Emit structured logs at each state transition (media_id, status, duration, error)
21. Emit metrics for processing durations and failure rates
22. Enforce tier limits before media creation (free tier: 5 media in default library)

**CRITICAL CONSTRAINT: Canonical Text Extraction Must Align With Highlight Model**
- The text extraction algorithm MUST produce `plain_text` that maps 1:1 to DOM rendering used for highlights
- Character offsets in `plain_text` MUST be stable and deterministic across re-ingestion
- For HTML/EPUB: extraction order MUST match DOM traversal order used by frontend highlight mapper
- For PDF: extraction order MUST match pdf.js text layer traversal order
- **For PDFs without text layers (scanned/image-only):**
  - Extraction produces `plain_text = ''` (empty string)
  - Media transitions to `ready_for_reading` (user can view PDF visually)
  - Chunking/embedding jobs are NOT enqueued (no text to process)
  - Media never transitions to `indexed`
  - Search behavior (semantic and keyword) is undefined for such media (search subsystem responsibility)
  - Highlight/annotation behavior for such media is out of scope for ingestion (reader subsystem responsibility)

This subsystem MUST NOT:

1. Make library permission decisions beyond default library auto-add
2. Manage library membership (add/remove users, change roles)
3. Create, read, update, or delete social objects (highlights, annotations, conversations)
4. Implement search queries (semantic or keyword)
5. Call LLMs for metadata repair, summarization, or content analysis
6. Enforce visibility rules (media is globally readable; enforcement is search subsystem responsibility)
7. Prompt users about duplicate content (deduplication is silent and automatic)
8. Extract, normalize, or disambiguate author metadata (deferred to metadata subsystem)
9. Select chunking strategies or embedding models (configured externally)
10. Implement text extraction algorithms (injected via interface)
11. Modify `plain_text` after reaching `ready_for_reading` (immutable)

## 4. External Interfaces

### 4.1 HTTP Endpoints

All endpoints require authentication. `user_id` is extracted from session/JWT.

#### POST /api/v1/media/upload-url

**Purpose:** Ingest media from a URL.

**Request:**
```json
{
  "url": "https://example.com/article",
  "kind": "html"
}
```

**Fields:**
- `url` (required, string): HTTP/HTTPS URL to fetch. Must be valid URL format.
- `kind` (optional, enum): One of `html`, `epub`, `pdf`. If omitted, inferred from Content-Type header.

**Response (201 Created):**
```json
{
  "media_id": "uuid",
  "processing_status": "pending",
  "canonical_url": "https://example.com/article",
  "created_at": "2025-01-15T10:30:00Z",
  "is_duplicate": false
}
```

**Response (200 OK, if duplicate detected):**
```json
{
  "media_id": "uuid",
  "processing_status": "indexed",
  "canonical_url": "https://example.com/article",
  "created_at": "2024-12-01T08:15:00Z",
  "is_duplicate": true
}
```

**Error Codes:**
- `400 INVALID_URL`: URL is malformed or unsupported protocol.
- `400 UNSUPPORTED_KIND`: `kind` is not `html`, `epub`, or `pdf` (if provided).
- `400 CONTENT_TYPE_MISMATCH`: Provided `kind` does not match fetched Content-Type.
- `403 TIER_LIMIT_EXCEEDED`: User has reached tier limit (free tier: 5 media in default library).
- `422 FETCH_FAILED`: URL fetch failed (timeout, 404, 5xx, network error).
- `422 CONTENT_TOO_LARGE`: Fetched content exceeds size limit.
- `422 UNSUPPORTED_CONTENT_TYPE`: Content-Type cannot be mapped to supported kind (when `kind` omitted).
- `500 INTERNAL_ERROR`: Unexpected server error.

**Behavior:**
1. Validate `url` format and `kind` enum (if provided).
2. Check user's tier limit by calling quota/billing subsystem: if limit exceeded, return `403 TIER_LIMIT_EXCEEDED`.
3. Fetch URL (10s timeout, follow up to 5 redirects, capture Content-Type header).
4. Canonicalize final redirected URL (lowercase scheme/host, sort query params, strip fragment, strip tracking params) and store as `canonical_url`.
5. Infer `kind` if not provided:
   - If `kind` provided: validate it matches Content-Type (fail with `400 CONTENT_TYPE_MISMATCH` if mismatch).
   - If `kind` not provided: infer from Content-Type (`text/html` → `html`, `application/pdf` → `pdf`, `application/epub+zip` → `epub`).
   - If Content-Type unknown: fallback to magic bytes detection.
   - If still cannot determine: fail with `422 UNSUPPORTED_CONTENT_TYPE`.
6. Compute content hash (SHA-256 of raw fetched bytes).
7. Attempt to insert `Media` row with `INSERT ... ON CONFLICT (content_hash) DO NOTHING RETURNING id`:
   - If row returned: new media created, proceed to step 9.
   - If no row returned: conflict on content_hash, query existing media by content_hash to get `media_id`.
8. If duplicate (content hash match): insert `LibraryMedia` row (idempotent), return `200` with `is_duplicate: true`.
9. If new: insert `LibraryMedia` row linking media to user's default library.
10. Enqueue `extract_media_task(media_id)` with task lock (idempotent; if already enqueued, skip).
11. Return `201` with `is_duplicate: false`.

**Deduplication Rules (Strict Content-Based Deduplication):**
- **Primary deduplication key:** content_hash (SHA-256 of raw fetched bytes)
  - Unique constraint on `media(content_hash)` enforces strict deduplication
  - Two media rows with identical content_hash MUST NOT exist (database-enforced)
  - All content_hash values MUST be populated (no NULL allowed in v1)
- **Secondary metadata:** canonical_url (stored as hint, NOT used for deduplication in v1)
  - Multiple different URLs MAY map to same media_id (if content identical)
  - Multiple different media_id MAY have identical canonical_url (if content differs)
- **Product-level deduplication semantics:**
  - "No duplicate documents" means "no two rows with identical bytes"
  - Does NOT mean "no two rows that are conceptually the same text" (e.g., different formatting)
  - Best-effort in product sense: cannot prevent logical duplicates (same article, different HTML)
  - Guaranteed in technical sense: no two rows with same content_hash
- First upload of content is canonical; subsequent uploads of identical content reuse existing `media_id`
- v1 does not support re-ingestion or content updates; if source content changes, users must manually remove and re-upload
- Canonicalization of URL (for storage): lowercase scheme/host, sort query params, strip fragment, strip tracking params (`utm_*`, `fbclid`, `gclid`, `_ga`, `ref`, `source`)

**Concurrency:**
- Content hash deduplication is enforced by database unique constraint on `media(content_hash)`
- Concurrent uploads with identical content will trigger constraint conflict; one succeeds, others retry with conflict resolution
- Task enqueue is idempotent; Celery task checks `processing_status` before starting

---

#### POST /api/v1/media/upload-file

**Purpose:** Ingest media from file upload.

**Request:** `multipart/form-data`
- `file` (required, file): EPUB or PDF file.
- `kind` (required, enum): One of `epub`, `pdf`. Must match file format.

**Response (201 Created):**
```json
{
  "media_id": "uuid",
  "processing_status": "pending",
  "storage_path": "uploads/uuid.pdf",
  "created_at": "2025-01-15T10:30:00Z",
  "is_duplicate": false
}
```

**Response (200 OK, if duplicate detected):**
```json
{
  "media_id": "uuid",
  "processing_status": "indexed",
  "storage_path": "uploads/original-uuid.pdf",
  "created_at": "2024-12-01T08:15:00Z",
  "is_duplicate": true
}
```

**Error Codes:**
- `400 MISSING_FILE`: No file provided.
- `400 UNSUPPORTED_KIND`: `kind` is not `epub` or `pdf`.
- `400 INVALID_FILE_TYPE`: File MIME type does not match `kind`.
- `403 TIER_LIMIT_EXCEEDED`: User has reached tier limit (free tier: 5 media in default library).
- `413 FILE_TOO_LARGE`: File size exceeds limit (PDF: 50 MB, EPUB: 25 MB).
- `500 INTERNAL_ERROR`: Storage upload failed or database error.

**Behavior:**
1. Validate `kind` enum (`epub` or `pdf`).
2. Validate file size: PDF ≤ 50 MB, EPUB ≤ 25 MB.
3. Validate file MIME type matches `kind` (magic bytes check: PDF = `%PDF`, EPUB = ZIP with `mimetype` entry).
4. Check user's tier limit by calling quota/billing subsystem: if limit exceeded, return `403 TIER_LIMIT_EXCEEDED`.
5. Compute content hash (SHA-256 of file bytes).
6. Attempt to insert `Media` row with `INSERT ... ON CONFLICT (content_hash) DO NOTHING RETURNING id`:
   - If row returned: new media created, proceed to step 8.
   - If no row returned: conflict on content_hash, query existing media by content_hash to get `media_id`.
7. If duplicate (content hash match): insert `LibraryMedia` row (idempotent), return `200` with `is_duplicate: true`.
8. If new: generate `storage_path` (opaque string, e.g., `uploads/{media_id}.{ext}`), upload file to object storage.
9. Insert `LibraryMedia` row linking media to user's default library.
10. Enqueue `extract_media_task(media_id)` to Celery.
11. Return `201` with `is_duplicate: false`.

**Idempotency:** Duplicate file uploads (same content hash) do not create new media rows or duplicate storage objects.

---

#### GET /api/v1/media/{media_id}

**Purpose:** Retrieve media metadata (not full content).

**Path Parameters:**
- `media_id` (required, UUID): Media ID.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "kind": "html",
  "canonical_url": "https://example.com/article",
  "title": "Article Title",
  "authors": [
    {"id": "uuid", "name": "Author Name"}
  ],
  "processing_status": "indexed",
  "failure_reason": null,
  "content_hash": "abc123...",
  "created_at": "2025-01-15T10:30:00Z",
  "processing_started_at": "2025-01-15T10:30:02Z",
  "processing_completed_at": "2025-01-15T10:32:15Z"
}
```

**Error Codes:**
- `404 MEDIA_NOT_FOUND`: Media ID does not exist.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `media` table by `id`.
2. Join `media_author` and `author` tables to retrieve authors (may be empty).
3. Return metadata object (excludes `plain_text` and `html` fields).

**Note:**
- Media is globally readable. No visibility check required.
- Authors are best-effort metadata; may be empty or incorrect.
- Full content (`plain_text`, `html`) is NOT returned to avoid bloating responses (especially for large PDFs).
- Use dedicated content endpoints to retrieve full text or HTML if needed.

---

#### GET /api/v1/media/{media_id}/content

**Purpose:** Retrieve media plain_text content (for backend processing, search result previews, or LLM context).

**Path Parameters:**
- `media_id` (required, UUID): Media ID.

**Response (200 OK):**
```json
{
  "media_id": "uuid",
  "plain_text": "Full plain text content..."
}
```

**Error Codes:**
- `404 MEDIA_NOT_FOUND`: Media ID does not exist.
- `422 CONTENT_NOT_READY`: Media processing_status is not `ready_for_reading` or `indexed`.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `media` table by `id`.
2. Verify `processing_status IN ('ready_for_reading', 'indexed')`.
3. Return `plain_text` field only.

**Note:**
- This endpoint is intended for backend subsystems (LLM, search) and advanced use cases, not for typical browser-based reading.
- For large PDFs, response may be several MB; clients should handle appropriately.
- Empty `plain_text` (scanned PDFs) returns empty string.

---

#### GET /api/v1/media/{media_id}/html

**Purpose:** Retrieve media display HTML (for HTML/EPUB reader rendering).

**Path Parameters:**
- `media_id` (required, UUID): Media ID.

**Response (200 OK):**
```json
{
  "media_id": "uuid",
  "html": "<article>...</article>"
}
```

**Error Codes:**
- `404 MEDIA_NOT_FOUND`: Media ID does not exist.
- `422 CONTENT_NOT_READY`: Media processing_status is not `ready_for_reading` or `indexed`.
- `422 NO_HTML_CONTENT`: Media kind is PDF (html field is NULL).
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `media` table by `id`.
2. Verify `processing_status IN ('ready_for_reading', 'indexed')`.
3. Verify `kind IN ('html', 'epub')` (PDFs have NULL html field).
4. Return `html` field only.

**Note:**
- This endpoint is used by the frontend reader to render HTML/EPUB media.
- PDF media do not have `html` content; use pdf.js with file from storage instead.

---

#### GET /api/v1/media

**Purpose:** List all media (global catalog) with pagination.

**OWNERSHIP NOTE:** This endpoint is currently owned by the ingestion subsystem for v1 simplicity, but conceptually belongs to a "media catalog" or "content access" surface. If per-media visibility or private documents are added in v2+, expect to move these catalog/listing endpoints to a separate subsystem. Do not treat this as permanent layering.

**Query Parameters:**
- `limit` (optional, int, default=50, max=100): Number of results per page.
- `offset` (optional, int, default=0): Pagination offset.
- `kind` (optional, enum): Filter by `html`, `epub`, or `pdf`.
- `status` (optional, enum): Filter by `pending`, `processing`, `ready_for_reading`, `indexed`, `failed`.

**Response (200 OK):**
```json
{
  "media": [
    {
      "id": "uuid",
      "kind": "html",
      "canonical_url": "https://example.com/article",
      "title": "Article Title",
      "authors": [{"id": "uuid", "name": "Author Name"}],
      "processing_status": "indexed",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 1234,
  "limit": 50,
  "offset": 0
}
```

**Behavior:**
1. Query `media` table with filters, ordering (`created_at DESC, id DESC`), and pagination.
2. Join `media_author` and `author` tables to retrieve authors (may be empty).
3. Return paginated results with total count.

---

#### GET /api/v1/media/{media_id}/status

**Purpose:** Poll processing status without fetching full content (optimized for progress tracking).

**Path Parameters:**
- `media_id` (required, UUID): Media ID.

**Response (200 OK):**
```json
{
  "media_id": "uuid",
  "processing_status": "processing",
  "failure_reason": null,
  "created_at": "2025-01-15T10:30:00Z",
  "processing_started_at": "2025-01-15T10:30:02Z",
  "processing_completed_at": null
}
```

**Error Codes:**
- `404 MEDIA_NOT_FOUND`: Media ID does not exist.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `media` table by `id` (select only status and timestamp columns, not content).
2. Return status object.

**Use Case:**
- Frontend progress bars showing upload → extraction → chunking → indexing flow
- Polling loops (recommended: 5s interval or long-polling)
- Lightweight alternative to GET /media/{id} when full content not needed

---

#### POST /api/v1/media/{media_id}/retry

**Purpose:** Retry failed media processing.

**Path Parameters:**
- `media_id` (required, UUID): Media ID.

**Response (202 Accepted):**
```json
{
  "media_id": "uuid",
  "processing_status": "pending",
  "failure_reason": null
}
```

**Error Codes:**
- `404 MEDIA_NOT_FOUND`: Media ID does not exist.
- `400 INVALID_STATE`: Media is not in `failed` status (retry only allowed for failed media).
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Begin database transaction with `SELECT FOR UPDATE` on `media` row by `id`.
2. Verify `processing_status = 'failed'`. If not, rollback and return `400 INVALID_STATE`.
3. Within transaction:
   a. Delete all rows from `chunk` table where `media_id = {media_id}` (all chunking strategies).
   b. Update `media` set `processing_status = 'pending'`, `failure_reason = NULL`, `processing_started_at = NULL`, `processing_completed_at = NULL`.
   c. Commit transaction.
4. After commit: enqueue `extract_media_task(media_id)` to Celery (idempotent).
5. Return `202`.

**Concurrency Semantics:**
- Row-level lock (`SELECT FOR UPDATE`) prevents concurrent retry requests on same media
- If media is currently being processed (race between failure write and retry), lock ensures serialization
- Multiple concurrent retry requests will serialize; only first will succeed, others will see non-failed state and return `400 INVALID_STATE`
- Chunk deletion and status reset are atomic within transaction
- Task enqueue after commit ensures state is consistent before background work begins

**Idempotency:** Multiple retry requests serialize via row lock; only first succeeds. Subsequent requests see `processing_status != 'failed'` and return error.

---

### 4.2 Background Jobs

**Retry Semantics (Clarification):**

All jobs are Celery tasks with two distinct failure modes and retry behaviors:

1. **Infrastructure failures** (Redis disconnects, broker errors, network timeouts):
   - Celery automatically retries task execution (max 3 attempts with exponential backoff)
   - If all retries exhausted: task body writes `processing_status = 'failed'` with appropriate `failure_reason`
   - Only the task body writes `failed` status; Celery itself does not write to database

2. **Domain failures** (extraction errors, parsing failures, corrupt files, DRM):
   - Task body catches exception, writes `processing_status = 'failed'` with `failure_reason`
   - Exception NOT re-raised to Celery (no automatic retry)
   - Requires manual retry via `/retry` endpoint

**Critical clarification:**
- Celery's retry mechanism only re-runs the task function
- State writes (`pending`, `processing`, `failed`) are always performed by task body, not Celery
- After Celery exhausts retries (3 failures), the final task execution writes `failed` status
- Manual `/retry` endpoint is orthogonal to Celery's automatic retry count

#### Task: `extract_media_task(media_id)`

**Purpose:** Extract text and generate canonical representations.

**Trigger:** Enqueued after media creation or retry.

**Preconditions:**
- `media.processing_status = 'pending'`
- `media.content_hash` OR `media.storage_path` is populated (depending on source)

**Behavior:**
1. Begin transaction with `SELECT FOR UPDATE` on `media` row by `media_id`.
2. If `processing_status != 'pending'`, rollback and abort (idempotency guard).
3. Update `processing_status = 'processing'`, `processing_started_at = now()`.
4. Commit transaction (releases lock; allows status polling).
5. **Dispatch to text extraction interface by kind:**
   - Interface contract: `extract_text(source, kind) -> (plain_text: str, html: str | null, title: str | null, metadata: dict)`
   - Implementation MUST be deterministic (same input → same output)
   - For PDF: MAY return empty `plain_text` if no text layer exists (scanned PDF)
   - For HTML/EPUB: `html` output MUST preserve reading order and map 1:1 to `plain_text` offsets
6. Validate extraction result:
   - For HTML/EPUB: `plain_text` MUST be non-empty (fail with `EXTRACTION_ERROR` if empty)
   - For PDF: `plain_text` MAY be empty (indicates scanned/image-only PDF; allowed)
   - `title` MAY be null (fallback: use filename or URL path)
   - `html` MUST be non-null for HTML/EPUB kinds, MUST be null for PDF kind
7. Extract authors from metadata (HTML `<meta name="author">`, EPUB `<dc:creator>`, PDF: none):
   - Split on separators (comma, " and ", " & ")
   - Trim whitespace from each name
   - For each author name: `INSERT INTO author (name) VALUES (...) ON CONFLICT (name) DO NOTHING` to get or create author_id
   - For each author_id: `INSERT INTO media_author (media_id, author_id) VALUES (...) ON CONFLICT DO NOTHING`
   - **CRITICAL:** Ingestion MUST NEVER update or delete existing author rows or media_author associations; it may only create new rows if they don't exist
   - Author extraction failure does NOT block processing (authors MAY be empty)
8. Begin transaction:
   - Update `media` set `plain_text`, `html`, `title`, `processing_status = 'ready_for_reading'`.
   - Commit transaction.
9. After commit:
   - If `plain_text` is non-empty: enqueue `chunk_media_task(media_id)` (idempotent).
   - If `plain_text` is empty: do NOT enqueue chunking (media remains at `ready_for_reading` permanently).
10. Emit log: `{"event": "media_extraction_complete", "media_id": "...", "duration_ms": 1234, "plain_text_length": 5000, "author_count": 2}`.

**Failure Handling:**
- On any exception during extraction or validation:
  1. Begin transaction.
  2. Update `processing_status = 'failed'`, `failure_reason = {error_code}`, `processing_completed_at = now()`.
  3. Commit transaction.
- Do NOT write partial results (no partial `plain_text`, no partial `html`).
- Error codes (enum values):
  - `FETCH_TIMEOUT`: URL fetch exceeded timeout.
  - `FETCH_ERROR`: HTTP error or network failure.
  - `PARSE_ERROR`: File parsing failed (corrupt file, unsupported format).
  - `EXTRACTION_ERROR`: Text extraction failed (DRM, no text layer, empty content).
  - `STORAGE_ERROR`: Object storage read failed.
- Emit log: `{"event": "media_extraction_failed", "media_id": "...", "error": "...", "failure_reason": "...", "duration_ms": 1234}`.
- Domain-level failures (PARSE_ERROR, EXTRACTION_ERROR, etc.) are caught and written to `failed` status WITHOUT re-raising for Celery retry.
- Infrastructure failures (Redis disconnects, broker errors) are retried by Celery automatically (max 3 attempts); after exhaustion, final task execution writes `failed` status (not Celery itself).

**Determinism Requirement (Critical):**
- Text extraction interface MUST be deterministic: same input → same `plain_text` every time
- Extraction order MUST be stable and match frontend highlight rendering traversal order
- No random sampling, no external API calls (except URL fetch), no LLM-based extraction
- For HTML: extraction order MUST match DOM traversal (depth-first, reading order)
- For EPUB: extraction order MUST match spine order + chapter DOM traversal
- For PDF: extraction order MUST match reading order (top-to-bottom, left-to-right per page)

**Transaction Boundaries:**
- Status transition `pending → processing`: atomic update with row lock
- Result write: atomic update with row lock
- Failure write: atomic update with row lock
- Isolation level: READ COMMITTED (prevents dirty reads during concurrent status polling)

---

#### Task: `chunk_media_task(media_id)`

**Purpose:** Chunk `plain_text` using the configured chunking strategy.

**Trigger:** Enqueued after extraction completes (`ready_for_reading` reached).

**Preconditions:**
- `media.processing_status = 'ready_for_reading'`
- `media.plain_text` is non-empty

**Behavior:**
1. Begin transaction with `SELECT FOR UPDATE` on `media` row by `media_id`.
2. If `processing_status != 'ready_for_reading'`, rollback and abort (idempotency guard).
3. Commit transaction (release lock).
4. Retrieve `plain_text` (immutable after this point).
5. Dispatch to chunking interface: `chunk_text(plain_text, strategy_config) -> List[Chunk]`
   - Interface returns list of chunks with `sequence_index` (0-indexed, sequential, gap-free)
   - Strategy identifier is stored in `chunking_strategy` column (v1 default: `recursive_character`)
6. Within a transaction:
   - Delete existing chunks for `(media_id, chunking_strategy)` (ensures atomicity on re-run).
   - Insert all new chunk rows: `media_id`, `chunking_strategy`, `sequence_index`, `content`, `embedding = NULL`.
   - Commit transaction.
7. After chunking completes: enqueue `embed_chunks_task(media_id, chunking_strategy)` (idempotent).
8. Emit log: `{"event": "media_chunking_complete", "media_id": "...", "strategy": "...", "chunk_count": 42}`.

**Failure Handling:**
- On exception during chunking:
  1. Begin transaction.
  2. Delete partial chunks for `(media_id, chunking_strategy)` if any were inserted.
  3. Update `processing_status = 'failed'`, `failure_reason = 'CHUNKING_ERROR'`.
  4. Commit transaction.
- Emit log: `{"event": "media_chunking_failed", "media_id": "...", "strategy": "...", "error": "..."}`.
- Domain-level failures are NOT automatically retried; infrastructure failures are retried by Celery (max 3 attempts), then final execution writes `failed`.

**Atomicity Constraint (Critical):**
- For `(media_id, chunking_strategy)`: either zero chunks exist, or a complete consistent chunk set exists
- No partial chunk sets allowed (enforced by delete-then-insert within transaction)
- `sequence_index` MUST be 0-indexed, sequential, gap-free (validated before insert)

**Transaction Boundaries:**
- Chunk insertion: atomic delete-then-insert within transaction
- Failure write: atomic status update
- Isolation level: READ COMMITTED

**Chunking Interface Contract:**
- Input: `plain_text` (string), `strategy_config` (dict with strategy-specific params)
- Output: List of `(sequence_index: int, content: str)` tuples
- MUST return sequential indices starting at 0 with no gaps
- MUST be deterministic (same input → same chunks)

---

#### Task: `embed_chunks_task(media_id, chunking_strategy)`

**Purpose:** Generate embeddings for all chunks of a given strategy.

**Trigger:** Enqueued after chunking completes for a strategy.

**Preconditions:**
- Chunks exist for `(media_id, chunking_strategy)` with `embedding IS NULL`
- `media.processing_status = 'ready_for_reading'`

**Behavior:**
1. Query `chunk` table by `media_id` and `chunking_strategy` where `embedding IS NULL`.
2. If no chunks found, abort (idempotency guard).
3. Batch chunks (batch size determined by embedding API rate limits; typically 100-1000).
4. For each batch:
   - Call embedding API interface: `generate_embeddings(texts: List[str]) -> List[np.ndarray]`
   - Within transaction: update `embedding` column for batch (pgvector type).
   - Commit transaction (per-batch commit for progress persistence).
5. After all chunks for this strategy have embeddings:
   - Verify completion: query to ensure ALL chunks for `(media_id, chunking_strategy)` have `embedding IS NOT NULL`
   - Begin transaction, update `media` set `processing_status = 'indexed'`, `processing_completed_at = now()`, commit.
   - **Invariant check:** Media may transition to `indexed` if and only if ALL configured chunking strategies for that media have complete embeddings (all chunks exist, all embeddings non-null).
6. Emit log: `{"event": "media_embedding_complete", "media_id": "...", "strategy": "...", "chunk_count": 42, "duration_ms": 5678}`.

**Failure Handling:**
- On exception during embedding:
  1. Begin transaction.
  2. Delete all chunks and embeddings for `(media_id, chunking_strategy)` to ensure clean state.
  3. Update `processing_status = 'failed'`, `failure_reason = 'EMBEDDING_ERROR'`.
  4. Commit transaction.
- Emit log: `{"event": "media_embedding_failed", "media_id": "...", "strategy": "...", "error": "..."}`.
- Do NOT retry automatically.
- On manual retry: all chunks and embeddings are already deleted (clean slate).

**Idempotency:**
- Embedding API interface MUST be deterministic (same input → same embedding)
- Task can be retried; skips chunks with existing embeddings
- Partial progress is preserved (per-batch commits)

**Transaction Boundaries:**
- Per-batch embedding update: atomic within transaction
- Final status transition to `indexed`: atomic update with row lock
- Isolation level: READ COMMITTED

**Embedding API Interface Contract:**
- Input: `texts` (list of strings), `model_config` (dict with model-specific params)
- Output: List of numpy arrays (fixed dimension, configured externally)
- MUST be deterministic (same input → same output)
- MUST handle rate limiting internally (exponential backoff)

**v1 Simplification:**
- Single chunking strategy per media (v1 default: `recursive_character`)
- Transition to `indexed` occurs immediately after embedding completes
- Multi-strategy support deferred to v2 (would require coordination logic and partial completion handling)

---

### 4.3 Events / Internal APIs

**v1 Implementation:**
This subsystem does not emit application-level events. Other subsystems poll database tables directly for state changes.

**Future Extension (v2+):**
Post-v1 may add events for:
- `media.indexed` → search subsystem cache warmup, analytics pipeline
- `media.failed` → user notifications, alerting
- `media.created` → analytics, recommendation engines

**Internal API contract (read-only database access):**

Other subsystems (search, library, reader) may:
- Query `media` table by `id`, `processing_status`, `canonical_url`.
- Query `chunk` table for semantic search (ANN queries on `embedding`).
- Query `author` and `media_author` tables for metadata display.

Constraints:
- Writes to `media`, `chunk` tables are restricted to ingestion subsystem only.
- Writes to `author`, `media_author` tables are allowed from ingestion subsystem and user-initiated author creation (see §2 Shared Ownership).
- `LibraryMedia` writes are allowed (library subsystem manages membership).

---

## 5. State & Lifecycles

### Media State Machine (Formal Definition)

**States:**
- `pending`: Initial state after media creation, awaiting extraction
- `processing`: Extraction in progress
- `ready_for_reading`: Text extraction complete, user can read, chunking/embedding in progress
- `indexed`: All processing complete, media is fully searchable
- `failed`: Processing failed at any stage, retry available

**Commands (external triggers):**
- `upload(url | file, kind, user_id)`: Create media, insert into default library, enqueue extraction
- `retry(media_id, user_id)`: Reset failed media to pending, delete chunks, re-enqueue extraction

**Internal Events (subsystem-triggered):**
- `extraction_started(media_id)`: Extraction task acquired lock, transitioned to processing
- `extraction_succeeded(media_id, plain_text, html, title)`: Extraction complete, transition to ready_for_reading
- `extraction_failed(media_id, error_code)`: Extraction failed, transition to failed
- `chunking_succeeded(media_id, strategy)`: Chunking complete for strategy, enqueue embedding
- `chunking_failed(media_id, strategy)`: Chunking failed, transition to failed
- `embedding_succeeded(media_id, strategy)`: Embedding complete for strategy, check if all strategies done
- `embedding_failed(media_id, strategy)`: Embedding failed, transition to failed
- `all_embeddings_complete(media_id)`: All strategies complete, transition to indexed

**State Transition Preconditions:**
- `pending → processing`: REQUIRES `processing_status = 'pending'` AND lock acquired
- `processing → ready_for_reading`: REQUIRES `processing_status = 'processing'` AND extraction succeeded
- `processing → failed`: REQUIRES `processing_status = 'processing'` AND extraction failed
- `ready_for_reading → indexed`: REQUIRES `processing_status = 'ready_for_reading'` AND embeddings complete
- `ready_for_reading → failed`: REQUIRES `processing_status = 'ready_for_reading'` AND (chunking OR embedding failed)
- `failed → pending`: REQUIRES `processing_status = 'failed'` AND user triggered retry AND lock acquired

**State Transition Postconditions:**
- `pending → processing`: `processing_started_at` set, lock released
- `processing → ready_for_reading`: `plain_text`, `html`, `title` populated, chunking tasks enqueued
- `processing → failed`: `failure_reason` populated, `processing_completed_at` set
- `ready_for_reading → indexed`: `processing_completed_at` set
- `ready_for_reading → failed`: `failure_reason` populated, `processing_completed_at` set
- `failed → pending`: `failure_reason` nulled, timestamps nulled, all chunks deleted

**Forbidden State Mutations:**
- Direct writes to `plain_text` after reaching `ready_for_reading` (immutable)
- Direct writes to `processing_status` outside defined transitions
- Deletion of chunks while `processing_status NOT IN ('failed', 'pending')`
- Concurrent state transitions on same media (prevented by row-level locks)

### Media Processing Lifecycle

```
┌─────────┐
│ pending │  Initial state after media creation
└────┬────┘
     │
     │ extract_media_task starts
     ▼
┌────────────┐
│ processing │  Text extraction in progress
└─────┬──────┘
      │
      │ Extraction succeeds
      ▼
┌───────────────────┐
│ ready_for_reading │  Text extraction complete, user can read
└─────┬─────────────┘  Chunking/embedding in progress
      │
      │ Chunking + embedding succeed
      ▼
┌─────────┐
│ indexed │  Fully searchable (semantic + keyword)
└─────────┘

      Any stage
      │
      │ Failure
      ▼
┌────────┐
│ failed │  Populated failure_reason, retry available
└────────┘
      │
      │ User triggers retry
      ▼
┌─────────┐
│ pending │  State reset, chunks deleted, re-enqueued
└─────────┘
```

**State Transition Rules:**

| From                | To                  | Trigger                                      | Forbidden Transitions              |
|---------------------|---------------------|----------------------------------------------|------------------------------------|
| `pending`           | `processing`        | `extract_media_task` starts                  | Cannot skip directly to `ready_for_reading` or `indexed` |
| `processing`        | `ready_for_reading` | Text extraction succeeds                     | Cannot return to `pending` (only `failed` or forward) |
| `processing`        | `failed`            | Extraction error                             | - |
| `ready_for_reading` | `indexed`           | Chunking + embedding succeed | Cannot return to `pending` or `processing` (only `failed` or forward) |
| `ready_for_reading` | `failed`            | Chunking or embedding error                  | - |
| `failed`            | `pending`           | User triggers retry                          | Cannot transition to any other state |
| `indexed`           | -                   | Terminal state (no transitions)              | Cannot transition to any state |

**Forbidden Transitions:**
- `pending` → `ready_for_reading` (must go through `processing`)
- `pending` → `indexed` (must go through `processing` → `ready_for_reading`)
- `processing` → `pending` (only `failed` can return to `pending` via retry)
- `ready_for_reading` → `pending` (only `failed` can return to `pending` via retry)
- `ready_for_reading` → `processing` (cannot revert)
- `indexed` → any state (terminal, immutable)

**Retry Semantics:**
- Only `failed` media can be retried.
- Retry resets `processing_status = 'pending'`, clears `failure_reason`, clears `processing_started_at` and `processing_completed_at`.
- Retry deletes ALL chunks and embeddings for `media_id`.
- Retry re-enqueues `extract_media_task(media_id)`.
- Idempotent: multiple retry requests for same `media_id` are safe.

---

## 6. Invariants

### Media Invariants

1. **Kind constraint:** `media.kind` MUST be one of `html`, `epub`, `pdf` (enforced by database enum). No other values allowed.
2. **Status constraint:** `media.processing_status` MUST be one of `pending`, `processing`, `ready_for_reading`, `indexed`, `failed` (enforced by database enum). No other values allowed.
3. **Source constraint:** `media.source` MUST be one of `upload`, `url` (enforced by database enum).
   - If `source = 'upload'`: `storage_path` MUST be non-null, `canonical_url` MUST be null.
   - If `source = 'url'`: `canonical_url` MUST be non-null, `storage_path` MAY be null (v1 does not persist fetched URL content).
4. **Canonical text immutability:** Once `processing_status` reaches `ready_for_reading`, `plain_text` MUST NOT be modified. Any modification MUST fail with constraint violation. Re-processing requires retry (which resets to `pending`).
5. **Deduplication (content-based, strict):** Two media rows with identical `content_hash` MUST NOT exist (enforced by unique constraint on `media(content_hash)`). Duplicate uploads reuse existing `media_id`. First upload is canonical; v1 does not support content updates or re-ingestion.
6. **Canonical URL semantics:** `canonical_url` is metadata only, NOT a deduplication key. Multiple distinct media rows MAY have identical `canonical_url` if their content differs (though this is rare). Conversely, multiple different URLs MAY map to the same media row if content is identical.
7. **Source tracking:** `media.uploader_user_id` MUST reference a valid `user.id` (foreign key constraint). This tracks who first uploaded the media (not ownership, since media is global).
8. **Default library auto-add:** When media is created via upload, a `LibraryMedia` row MUST be inserted linking the media to the uploader's default library (`library.is_default = true`). Insert is idempotent (unique constraint on `(library_id, media_id)`).
9. **Failure reason enum:** `failure_reason` is a database enum with values: `FETCH_TIMEOUT`, `FETCH_ERROR`, `PARSE_ERROR`, `EXTRACTION_ERROR`, `STORAGE_ERROR`, `CHUNKING_ERROR`, `EMBEDDING_ERROR`. If `processing_status = 'failed'`, `failure_reason` MUST be non-null and contain valid enum value. If `processing_status != 'failed'`, `failure_reason` MUST be null.
10. **Processing timestamps:** `processing_started_at` is set when status → `processing`. `processing_completed_at` is set when status → `indexed` or `failed`. Both MUST be null in `pending` state.
11. **HTML nullability:** For `kind = 'pdf'`, `html` is unused in v1 and SHOULD be `NULL` (PDF rendering uses pdf.js on frontend). For `kind IN ('html', 'epub')`, `html` MUST be non-null after reaching `ready_for_reading`. Future versions may populate `html` for PDFs with normalized text representation for unified highlight code paths.
12. **Storage path lifecycle:**
    - For `source = 'upload'`: `storage_path` MUST be non-null and reference valid object storage location (opaque string, e.g., `uploads/{media_id}.{ext}`).
    - For `source = 'url'`: `storage_path` MAY be null (fetched content not persisted in v1).
    - Storage objects are NEVER deleted in v1 (no garbage collection; orphan cleanup deferred to v2).
    - Storage objects are immutable once written (no updates).
13. **Content hash presence:** `content_hash` (SHA-256, 64 hex chars) MUST be non-null after media creation. Used for deduplication and integrity verification.
14. **Plain text nullability:** `plain_text` MAY be empty for PDFs without text layers (scanned/image-only). For HTML/EPUB, `plain_text` MUST be non-empty after reaching `ready_for_reading`. Empty `plain_text` for HTML/EPUB indicates extraction failure; such media MUST NOT reach `ready_for_reading`.
15. **Empty plain text behavior (scanned PDFs):** For media with `plain_text = ''`:
    - Media reaches `ready_for_reading` (user can view visually)
    - Chunking jobs are NOT enqueued
    - Media never transitions to `indexed`
    - Search behavior (semantic and keyword) is out of scope for ingestion (search subsystem responsibility)
    - Highlight/annotation behavior is out of scope for ingestion (reader subsystem responsibility)

### Chunk Invariants

1. **Atomicity:** For each `(media_id, chunking_strategy)`, either zero chunks exist, or a complete consistent chunk set exists. No partial chunk sets allowed.
2. **Sequence ordering:** `sequence_index` MUST be 0-indexed, sequential, and gap-free for each `(media_id, chunking_strategy)`. Sequence `[0, 1, 2, 5]` is invalid (gap at 3, 4).
3. **Uniqueness:** `(media_id, chunking_strategy, sequence_index)` is unique (enforced by database constraint).
4. **Embedding nullability:** `embedding` MAY be null after chunking, MUST be non-null after embedding task completes. Null embeddings indicate incomplete indexing.
5. **Re-chunking:** Re-chunking for a given `(media_id, chunking_strategy)` MUST delete all existing chunks for that pair before inserting new chunks.

### Author Invariants

1. **Best-effort extraction:** Authors are extracted from document metadata at ingestion (HTML `<meta name="author">`, EPUB `<dc:creator>`, PDF: none in v1). Extraction is best-effort; failure does not block processing.
2. **Deduplication:** `author.name` is unique (enforced by database constraint). Duplicate author names reuse existing `author_id`.
3. **No normalization:** v1 uses exact string match. No case-folding, no disambiguation, no external lookups. "John Smith" and "J. Smith" are distinct authors.
4. **Association uniqueness:** `(media_id, author_id)` in `media_author` is unique. A media cannot be linked to the same author twice.
5. **Zero authors allowed:** Media may have zero authors. Absence of authors does not block processing or indicate failure.
6. **Splitting rules:** Author strings containing separators (comma, " and ", " & ") are split into multiple author names. Whitespace is trimmed.
7. **Immutability (ingestion subsystem):** Ingestion MUST NEVER update or delete existing `author` rows or `media_author` associations. It may only create new rows that don't already exist.
8. **User creation:** Users may create new authors via UI (manual metadata entry). v1 constraint: users CANNOT edit or delete authors (create-only).
9. **Non-authoritative:** Author correctness is not guaranteed. Future metadata subsystem may support author editing, merging, and disambiguation (out of scope for v1 ingestion).

### Deduplication Invariants

1. **Content hash (strict):** Two uploaded files with identical SHA-256 content hash MUST reuse the same `media_id`. No duplicate storage. Enforced by unique constraint on `media(content_hash)`.
2. **Content hash population:** All media rows MUST have non-NULL `content_hash` after creation. No exceptions in v1.
3. **Canonical URL (metadata only):** `canonical_url` is NOT a deduplication key. Two uploads with identical `canonical_url` but different content will create separate media rows. Two uploads with different `canonical_url` but identical content will reuse the same media row.
4. **Product-level deduplication (best-effort):** "No duplicate documents" is best-effort at the product level (cannot prevent conceptually-same content with different bytes). Guaranteed only at technical level (no two rows with same bytes).
5. **Library membership idempotency:** If media M already exists and user U uploads M again, inserting `LibraryMedia(library_id=U.default_library_id, media_id=M.id)` MUST be idempotent (no duplicate rows, no error).
6. **Deduplication transparency:** User is informed via `is_duplicate: true` in response. No confirmation prompt required.

### Tier Limit Invariants

**CRITICAL: Cross-Cutting Policy Coupling**

Ingestion is coupled to the quota/billing subsystem for tier limit enforcement. This is a design choice, not an inherent requirement. Realize this creates:
- Direct coupling: every upload path invokes quota/billing check
- Failure mode: if quota/billing subsystem unavailable, uploads fail (not just billing)
- Testing complexity: quota/billing must be mocked/stubbed in ingestion tests

**Recommended mitigation:** Centralize the "can user add media?" check in a single helper function, not sprinkled across upload endpoints. This isolates the coupling point and makes future refactoring easier.

1. **Enforcement delegation:** Ingestion subsystem calls quota/billing subsystem to check "can this user add media now?" before media creation.
2. **Enforcement timing:** Tier limit check occurs BEFORE media creation. Upload fails with `403 TIER_LIMIT_EXCEEDED` if limit reached.
3. **Business rules (owned by quota/billing subsystem, not ingestion):**
   - Free tier: maximum 5 media in default library
   - Personal/Pro tiers: unlimited media
   - Retroactive enforcement: if user downgrades, they cannot add NEW media, but existing media remains accessible (enforcement is additive-only)
4. **Ingestion responsibility:** Ingestion MUST call the quota check but MUST NOT hardcode tier-specific limits or business logic. Limits are configuration in quota/billing subsystem.

---

## 7. Error Handling

### Upload Errors

| Error Code              | HTTP Status | Meaning                                      | User Action                          |
|-------------------------|-------------|----------------------------------------------|--------------------------------------|
| `INVALID_URL`           | 400         | URL is malformed or unsupported protocol     | Fix URL format                       |
| `UNSUPPORTED_KIND`      | 400         | `kind` is not `html`, `epub`, or `pdf` (if provided) | Use valid kind                |
| `CONTENT_TYPE_MISMATCH` | 400         | Provided `kind` does not match fetched Content-Type | Check URL or omit `kind` parameter |
| `MISSING_FILE`          | 400         | File upload missing                          | Provide file                         |
| `INVALID_FILE_TYPE`     | 400         | File MIME type does not match `kind`         | Upload correct file type             |
| `FILE_TOO_LARGE`        | 413         | File size exceeds limit (PDF: 50MB, EPUB: 25MB) | Compress or split file            |
| `TIER_LIMIT_EXCEEDED`   | 403         | User has reached tier limit (free: 5 media)  | Upgrade subscription or remove media |
| `FETCH_FAILED`          | 422         | URL fetch failed (timeout, 404, 5xx)         | Check URL or retry                   |
| `CONTENT_TOO_LARGE`     | 422         | Fetched content exceeds size limit           | Cannot process this URL              |
| `UNSUPPORTED_CONTENT_TYPE` | 422      | Content-Type cannot be mapped to supported kind (when `kind` omitted) | Provide `kind` parameter explicitly |
| `INTERNAL_ERROR`        | 500         | Unexpected server error                      | Retry or contact support             |

### Processing Errors (stored in `failure_reason`)

| Error Code          | Cause                                        | Retry Behavior                          |
|---------------------|----------------------------------------------|-----------------------------------------|
| `FETCH_TIMEOUT`     | URL fetch exceeded 10s timeout               | Safe to retry (transient network issue) |
| `FETCH_ERROR`       | HTTP 4xx/5xx or network error                | Safe to retry (may be transient)        |
| `PARSE_ERROR`       | File parsing failed (corrupt EPUB/PDF)       | Unlikely to succeed on retry (bad file) |
| `EXTRACTION_ERROR`  | Text extraction failed (DRM, unsupported PDF features) | Unlikely to succeed on retry (DRM or unsupported format) |
| `STORAGE_ERROR`     | Object storage read failed                   | Safe to retry (transient storage issue) |
| `CHUNKING_ERROR`    | Chunking logic crashed                       | Safe to retry (may be transient)        |
| `EMBEDDING_ERROR`   | Embedding API failed (timeout, rate limit, API error) | Safe to retry (transient API issue) |

**Retry Strategy:**
- User must manually trigger retry via `POST /media/{media_id}/retry`.
- Automatic retry is NOT implemented in v1 (avoids infinite loops, costly retries).
- Retry wipes all chunks/embeddings and resets to `pending`.

**Failure Reason Display:**
- `failure_reason` is shown to user in UI with plain-English explanation:
  - `FETCH_TIMEOUT` → "The URL took too long to load. Please try again."
  - `PARSE_ERROR` → "The file is corrupt or unsupported. Please upload a different file."
  - `EXTRACTION_ERROR` → "Text extraction failed. This file may be protected by DRM."
  - `EMBEDDING_ERROR` → "Indexing failed due to a temporary issue. Please retry."

---

## 8. Performance, Limits, and Pagination

**CRITICAL DISTINCTION: Protocol Guarantees vs Operational Configuration**

This section distinguishes between:
1. **Protocol-level guarantees** (hard requirements for correctness)
2. **Operational configuration** (tunables for performance/cost optimization)

### File Size Limits

**Protocol guarantee (hard requirement):**
- Ingestion MUST have some maximum file size limit to prevent resource exhaustion
- Ingestion MUST reject files exceeding the limit with appropriate error codes
- Limits MUST be enforced before significant processing (storage upload, extraction)

**Operational configuration (suggested defaults, not mandated):**

| Media Kind | Suggested Default | Notes |
|------------|-------------------|-------|
| PDF        | 50 MB             | Tunable based on storage capacity and processing time tolerance |
| EPUB       | 25 MB             | Tunable based on extraction performance |
| HTML (URL) | 10 MB (fetched)   | Tunable based on network timeout and memory constraints |

**Note:** Actual values are deployment-specific and should be externally configurable (environment variables, database config). Do not hardcode in application logic.

**Enforcement:**
- File upload: validated before storage upload (HTTP 413 if exceeded).
- URL fetch: validated after download (HTTP 422 if exceeded).

### Plain Text Size Limits

**Protocol guarantee (hard requirement):**
- Ingestion MUST have a maximum `plain_text` length limit to prevent database bloat and downstream processing failures
- If extraction produces `plain_text` exceeding the limit, ingestion MUST handle gracefully (options below)
- Limit MUST be externally configurable

**Operational configuration (suggested approach):**

| Limit Type | Suggested Value | Strategy |
|------------|-----------------|----------|
| Hard limit (reject) | 10 million characters | Fail ingestion with `EXTRACTION_ERROR` if exceeded |
| Warning threshold | 5 million characters | Log warning but allow (monitor for performance impact) |

**Handling strategies (choose one):**
1. **Reject extraction:** Fail with `EXTRACTION_ERROR` if `plain_text` exceeds limit (strictest)
2. **Truncate:** Store first N characters, mark media as `ready_for_reading` but not `indexed` (partial indexing)
3. **Stream/chunk during extraction:** Never materialize full `plain_text` in memory (complex, deferred to v2)

**Recommended for v1:** Reject extraction (strategy 1) with clear error message. This prevents edge cases (2GB text file) from degrading system performance.

**Note:** This limit is separate from file size limit. A 50MB PDF may extract to 20MB of text; both limits must be enforced.

### Processing Timeouts

**Protocol guarantee (hard requirement):**
- All processing stages MUST have finite timeouts (no infinite loops or hangs)
- Timeout violations MUST surface as `failed` status with `failure_reason` populated
- Timeout configuration MUST be externally tunable (not hardcoded)

**Operational configuration (suggested defaults, not mandated):**

| Task                  | Suggested Default | Notes |
|-----------------------|-------------------|-------|
| URL fetch             | 10s               | Balance between slow servers and user patience |
| Extraction            | 5 min             | Large PDFs may need longer; monitor p95 processing time |
| Chunking              | 2 min             | Should be sub-minute for typical docs; tune if seeing failures |
| Embedding (per batch) | 30s               | API-dependent; adjust based on provider SLA |

**Note:** These are operational tunables, not correctness requirements. Tune based on observed production performance, error rates, and user feedback.

**Timeout Behavior:**
- On timeout: task fails, `processing_status = 'failed'`, `failure_reason` populated.
- Celery task retry: max 3 attempts with exponential backoff (suggested: 2s, 4s, 8s; configurable).

### Tier Limits

| Tier     | Max Media in Default Library |
|----------|------------------------------|
| Free     | 5                            |
| Personal | Unlimited                    |
| Pro      | Unlimited                    |

**Enforcement Point:** Upload endpoints check tier limit BEFORE creating media row.

### Pagination

**GET /api/v1/media:**
- **v1 implementation:** Offset-based pagination (simple but not stable under concurrent writes)
  - Default `limit`: 50
  - Max `limit`: 100
  - Default `offset`: 0
  - Ordering: `created_at DESC, id DESC` (deterministic secondary sort on id)
  - Response includes `total` count (total matching media, not total pages).
- **v2 migration plan:** Cursor-based pagination (stable under concurrent writes)
  - Cursor format: base64-encoded `(created_at, id)` tuple
  - No offset skipping (forward-only iteration)
  - No total count (expensive to compute at scale)

**Offset Pagination Issues (Known Limitations):**
- Concurrent inserts can cause duplicate results across pages (acceptable for v1)
- Concurrent deletes can cause skipped results (acceptable for v1)
- Offset skipping is inefficient at large offsets (e.g., page 1000 requires scanning 50k rows)
- Total count is expensive for large datasets (requires full table scan with filters)

**Example (v1):**
```
GET /api/v1/media?limit=50&offset=0  # Page 1
GET /api/v1/media?limit=50&offset=50 # Page 2
```

**Ordering Stability:**
- MUST use deterministic ordering (created_at DESC, id DESC)
- Secondary sort on `id` ensures consistency when `created_at` is identical
- Without secondary sort, pagination is non-deterministic

### Performance Guidance

**Upload latency:** Should complete in seconds for typical files; sub-second for duplicates.

**Processing pipeline:** Should complete within single-digit minutes for typical documents; anything longer is considered degraded service.

**Note:** Specific SLOs should be defined based on observed production performance and user expectations, not prescribed in advance.

---

## 9. Observability

**Requirements:**
- Ingestion MUST emit structured logs at each state transition (JSON format)
- Logs MUST include: `media_id`, `event` name, `processing_status`, timing data
- Ingestion SHOULD expose basic metrics: upload counts, processing durations, failure counts
- Logs SHOULD be queryable by `media_id`, `user_id`, `processing_status`

**Recommended events to log:**
- Media upload (new vs duplicate)
- State transitions (`pending` → `processing` → `ready_for_reading` → `indexed`)
- Failures (with `failure_reason` and error context)
- Retry triggers

**Metrics guidance:**
- Counters: upload requests, extraction/chunking/embedding jobs (success/failure)
- Histograms: processing durations by stage and media kind
- Gauges: active processing count, failed media count

**Note:** Specific metric names, alert thresholds, and log aggregation infrastructure are deployment-specific and should be defined in a separate observability configuration document.

---

## 10. Test Matrix

### Unit Tests

| Test Case                                  | Inputs                                   | Expected Output                              | Invariants Validated                     |
|--------------------------------------------|------------------------------------------|----------------------------------------------|------------------------------------------|
| Upload HTML URL (new)                      | Valid URL, `kind=html`                   | 201, `media_id`, `is_duplicate=false`        | Media row created, status=`pending`      |
| Upload HTML URL (duplicate)                | Existing URL, `kind=html`                | 200, existing `media_id`, `is_duplicate=true`| No new media row, LibraryMedia inserted  |
| Upload PDF file (new)                      | Valid PDF file, `kind=pdf`               | 201, `media_id`, `is_duplicate=false`        | File uploaded to storage, media row created   |
| Upload PDF file (duplicate content hash)   | Duplicate file, `kind=pdf`               | 200, existing `media_id`, `is_duplicate=true`| No new storage object, LibraryMedia inserted  |
| Upload file too large                      | 60 MB PDF, `kind=pdf`                    | 413, `FILE_TOO_LARGE`                        | No media row created                     |
| Upload unsupported kind                    | `kind=mp3`                               | 400, `UNSUPPORTED_KIND`                      | No media row created                     |
| Upload with tier limit reached (free tier) | User has 5 media, uploads 6th            | 403, `TIER_LIMIT_EXCEEDED`                   | No media row created                     |
| Fetch URL timeout                          | URL takes >10s to respond                | 422, `FETCH_FAILED`                          | No media row created                     |
| Extract HTML (success)                     | Valid HTML media                         | Status transitions `pending`→`processing`→`ready_for_reading` | `plain_text`, `html` populated, non-empty |
| Extract EPUB (success)                     | Valid EPUB media                         | Status transitions to `ready_for_reading`    | `plain_text`, `html` populated, non-empty |
| Extract PDF (success)                      | Valid PDF media                          | Status transitions to `ready_for_reading`    | `plain_text` populated, `html=NULL`, non-empty |
| Extract PDF with no text layer             | Scanned PDF (no text)                    | Status transitions to `ready_for_reading`, `plain_text=''`, no chunking enqueued | Empty `plain_text` allowed for PDFs; media viewable but not indexable |
| Extract with parse error                   | Corrupt PDF                              | Status transitions to `failed`, `failure_reason=PARSE_ERROR` | No chunks created |
| Extract with DRM                           | DRM-protected EPUB                       | Status transitions to `failed`, `failure_reason=EXTRACTION_ERROR` | No chunks created |
| Chunk media (recursive_character)          | Media with `plain_text`                  | Chunks created with `chunking_strategy=recursive_character`, sequential `sequence_index` | Atomicity: all chunks or none |
| Embed chunks (success)                     | Chunks with `embedding=NULL`             | All chunks have `embedding` populated, status→`indexed` | All embeddings non-null |
| Embed chunks (API failure)                 | Embedding API returns 500                | Status→`failed`, `failure_reason=EMBEDDING_ERROR` | Partial embeddings rolled back |
| Retry failed media                         | Media with `status=failed`               | Status→`pending`, all chunks deleted, re-enqueued | Idempotency: safe to retry multiple times |
| Retry non-failed media                     | Media with `status=indexed`              | 400, `INVALID_STATE`                         | No state change                          |
| GET /media/{id}                            | Existing `media_id`                      | 200, full media object with authors          | Global readability (no auth check)       |
| GET /media/{id} (not found)                | Non-existent `media_id`                  | 404, `MEDIA_NOT_FOUND`                       | -                                        |
| GET /media (list, paginated)               | `limit=10, offset=0`                     | 200, 10 media, `total` count                 | Pagination works correctly               |
| GET /media (filter by kind)                | `kind=pdf`                               | 200, only PDF media returned                 | Filter applied correctly                 |
| GET /media (filter by status)              | `status=indexed`                         | 200, only indexed media returned             | Filter applied correctly                 |

### Integration Tests

| Test Case                                  | Flow                                     | Expected Outcome                             | Invariants Validated                     |
|--------------------------------------------|------------------------------------------|----------------------------------------------|------------------------------------------|
| End-to-end HTML upload                     | Upload URL → extract → chunk → embed    | Media reaches `indexed`, searchable          | Full pipeline completes successfully     |
| End-to-end EPUB upload                     | Upload file → extract → chunk → embed   | Media reaches `indexed`, `plain_text` + `html` populated | Full pipeline completes successfully     |
| End-to-end PDF upload                      | Upload file → extract → chunk → embed   | Media reaches `indexed`, `html=NULL`, `plain_text` populated | Full pipeline completes successfully     |
| Duplicate upload (same user)               | Upload same URL twice                    | Second upload returns existing `media_id`, no duplicate chunks | Deduplication works, LibraryMedia idempotent |
| Duplicate upload (different users)         | User A uploads URL, User B uploads same URL | Both users have media in their default libraries, same `media_id` | Deduplication works, both users linked |
| Tier limit enforcement                     | Free tier user uploads 6th media         | 6th upload fails with `TIER_LIMIT_EXCEEDED`  | Tier limit enforced at upload time       |
| Retry after extraction failure             | Upload corrupt PDF → retry               | First attempt fails, retry re-enqueues, second attempt fails again | Retry resets state correctly |
| Retry after chunking failure               | Extract succeeds, chunking fails → retry | Retry deletes partial chunks, re-chunks      | Chunk atomicity maintained               |
| Concurrent retry requests                  | Two retry requests at same time          | Only one succeeds, other returns `INVALID_STATE` | Row-level locking prevents race         |
| Celery task idempotency                    | Re-enqueue same task twice               | Second task aborts (status guard)            | No duplicate processing                  |
| Concurrent duplicate uploads               | Same URL uploaded by two users simultaneously | One succeeds, others retry with conflict resolution | Unique constraint on content_hash prevents duplicates |

### Load Tests

| Test Case                                  | Scale                                    | Expected Performance                         |
|--------------------------------------------|------------------------------------------|----------------------------------------------|
| Concurrent uploads                         | 100 uploads/sec                          | All uploads succeed, queue not overwhelmed   |
| Large file upload                          | 50 MB PDF                                | Upload completes in <2s, processing in <120s |
| Media list pagination                      | 10,000 media in system, query page 50    | Response time <200ms                         |
| Embedding API batch size                   | 1000 chunks, batch=100                   | All embeddings generated in <60s             |

---

## 11. Open Questions

### Resolved (v1 decisions committed)

1. **Q:** Should PDF uploads store original file in S3?
   **A:** Yes. `storage_path` stores S3 URI for all uploaded files (EPUB, PDF). HTML fetched from URL is not stored in S3 (can be re-fetched if needed, out of scope for v1).

2. **Q:** Should deduplication prompt user for confirmation?
   **A:** No. Deduplication is silent and automatic. User is informed via `is_duplicate: true` in response, but no confirmation prompt is shown.

3. **Q:** Should failed media be automatically retried?
   **A:** No. Automatic retry is not implemented in v1. User must manually trigger retry via `/retry` endpoint. This avoids infinite loops and costly retries for persistently failing content.

4. **Q:** Should chunking strategies be configurable per media?
   **A:** Deferred to implementation. Chunking strategies are configured externally; ingestion subsystem is strategy-agnostic. Default v1 configuration applies all configured strategies to all media.

5. **Q:** Should `plain_text` be versioned?
   **A:** No. v1 does not version `plain_text`. Once `ready_for_reading` is reached, `plain_text` is immutable. Re-processing requires deletion and recreation (out of scope for v1).

### Open (require product decision before implementation)

**CRITICAL - MUST RESOLVE BEFORE IMPLEMENTATION BEGINS:**

**Blocking implementation:** Yes
**Deadline for decision:** Before sprint planning
**Decision maker:** Product owner

1. **Q:** Text Extraction Alignment Specification
   **A:** UNRESOLVED. Requires separate specification document defining:
   - **Who:** Frontend + backend engineers collaborate
   - **When:** Before extraction algorithm selection
   - **What:** Document exact traversal rules for each kind:
     - HTML: depth-first DOM traversal, reading-order heuristics for complex layouts (tables, sidebars, multi-column)
     - EPUB: spine order + per-chapter DOM traversal rules
     - PDF: pdf.js text layer extraction order (top-to-bottom, left-to-right per page)
   - **Validation:** Automated test suite comparing extraction output with frontend highlight offset calculations
   - **Edge cases:** How to handle embedded objects, footnotes, annotations, multi-column text, RTL languages
   - **Rationale:** Without alignment spec, highlight offsets will be incorrect and user experience will be broken

2. **Q:** Scanned PDFs - product behavior
   **A:** UNRESOLVED. This spec defines technical behavior (extraction produces `plain_text = ''`, no chunking/indexing). Product must decide:
   - v1: View-only, no highlights, no search (strictest; requires reader subsystem to check for empty `plain_text`)
   - v1: View-only, with placeholder for future OCR (allows highlights after OCR added)
   - This decision affects reader subsystem spec, not ingestion technical behavior.

**Implementation choices (non-blocking; can be decided during implementation):**

These decisions do not block the spec but must be made before coding begins. They should be documented in a separate `ingestion-implementation.md` file:

3. **Q:** Text extraction libraries
   - HTML: mozilla/readability, trafilatura, or newspaper3k?
   - EPUB: ebooklib or calibre?
   - PDF: PyMuPDF, pdfplumber, or pdfminer.six?
   - **Constraint:** Must be deterministic, must align with highlight traversal order

4. **Q:** Chunking strategy
   - Recommended: `recursive_character` with 1000 char chunks, 200 char overlap
   - **Constraint:** Must be deterministic

5. **Q:** Embedding model
   - Recommended: OpenAI `text-embedding-3-small` (1536d)
   - **Constraint:** Must be deterministic

**Lower priority (can be deferred):**

6. **Q:** Should media support OCR for scanned PDFs?
   **A:** Out of scope for v1. Scanned PDFs remain at `ready_for_reading` (viewable but not searchable).

---

## 12. Future Extensions

**Note:** These are potential future directions, not commitments. Priority and scope will be determined post-v1 based on user feedback and product roadmap.

**Potential post-v1 enhancements:**
- OCR support for scanned PDFs
- Automatic retry with exponential backoff
- Media deletion (requires cascade handling)
- Re-processing pipeline (algorithm improvements without losing social objects)
- Additional media kinds (transcripts, podcasts)
- Multi-language support
- Metadata editing/disambiguation (requires separate metadata subsystem spec)
- Content moderation integration
- Incremental content updates
- Private media (requires significant architecture rework)

---

## End of Specification

**Status: DRAFT**

This document defines the complete interface contract and invariants for the ingestion subsystem. It is implementation-ready AFTER resolving the four critical open questions in §11:
1. Text extraction algorithm selection (HTML/EPUB/PDF)
2. Chunking strategy and parameters
3. Embedding model selection
4. Text extraction alignment specification

Until those decisions are made and documented, this spec remains in DRAFT status.

**Post-resolution:**
- All ambiguities have been resolved
- Deviations from invariants are forbidden
- Questions must be escalated to product owner
