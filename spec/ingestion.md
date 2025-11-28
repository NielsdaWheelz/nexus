# Ingestion Pipelines & Canonicalization

## 1. Ingestion Overview

Document ingestion is a multi-step asynchronous pipeline orchestrated by Celery:

```
[Upload] → ingest_document → canonicalize_document → chunk_and_embed_document → [Ready]
                                        ↓
                              (hash changed?) → remap_highlights
```

All steps are **idempotent**: re-running with same inputs produces same results.

### 1.1 Reprocessing & Re-ingestion

Re-ingestion is triggered **only** in the following scenarios:

1. **Manual admin request**: Admin explicitly triggers re-processing via operational interface
2. **System-level migration**: Platform-wide re-extraction (e.g., upgrading extraction code with breaking changes)

Re-ingestion is **NOT** automatically triggered by:
- Extraction code updates (new code only applies to new uploads)
- Configuration changes (extraction parameters are not stored)

### 1.2 Re-ingestion Pipeline

When re-ingestion occurs:

```
[Admin triggers re-process] → ingest_document (with original_blob_key)
                                        ↓
                           hash original blob
                                        ↓
                           compare with existing content_hash
                                        ↓
        ┌─────────────────────┼─────────────────────┐
        ↓                     ↓                     ↓
  [hash unchanged]    [hash changed]         [original blob missing]
        ↓                     ↓                     ↓
   [skip extract]    canonicalize_document  [error: blob not found]
        ↓                     ↓
   [done]            [new canonical_text]
                              ↓
                      [compute new canonical_hash]
                              ↓
                      ┌────────┼────────┐
                      ↓                 ↓
                 [hash same]      [hash changed]
                      ↓                 ↓
                   [done]         [enqueue remap_highlights]
                                        ↓
                            chunk_and_embed_document
                                        ↓
                                   [ready]
```

**Original blob immutability**: The `original_blob_key` is looked up in S3 and MUST be present. If the blob has been deleted, re-ingestion fails with `ERR_BLOB_NOT_FOUND`.

---

## 2. Phase 1 Ingestion Jobs

### 2.1 Job: `ingest_document`

**Purpose**: Download blob from S3, compute hash, prepare for canonicalization.

**Inputs**:

```typescript
{
  document_id: UUID,
  blob_key: string,      // S3 key
  user_id: UUID
}
```

**Preconditions**:

- Document exists with `status = 'pending'`
- Blob uploaded to S3 at `blob_key`

**Idempotency key**:

```
(document_id, content_hash)
```

If `content_hash` unchanged and `canonical_text` exists, skip.

**Execution**:

1. Download blob from S3
2. Compute `content_hash = SHA256(blob)`
3. Update document: `SET content_hash = $1 WHERE id = $2`
4. Enqueue `canonicalize_document`

**Success postconditions**:

- `content_hash` set
- `canonicalize_document` job enqueued

**Failure postconditions**:

- `status = 'failed'`
- `error_code = 'blob_download_failed' | 'hash_computation_failed'`

**Retry policy**:

- Max attempts: 3
- Backoff: 1m, 5m, 15m

---

### 2.2 Job: `canonicalize_document`

**Purpose**: Extract canonical text, update document, prepare for chunking and remapping.

**Inputs**:

```typescript
{
  document_id: UUID
}
```

**Preconditions**:

- Document has `content_hash` set
- Blob exists in S3

**Idempotency key**:

```
(document_id, content_hash, extractor_version)
```

If `canonical_text` exists with matching `content_hash` and `extractor_version`, skip.

**Execution**:

1. Download blob from S3
2. Detect format (PDF/EPUB/HTML)
3. Extract canonical text per [spec/media.md](media.md) §2.3
4. Compute `canonical_hash = SHA256(canonical_text)`
5. Determine if hash changed:
   - If no prior `canonical_text`: new hash computed (no prior to compare)
   - If existing `canonical_hash` differs: hash changed, remap will be triggered
   - If existing `canonical_hash` same: hash unchanged, no remap needed
6. Extract structure (blocks, sections, headings)
7. Extract metadata (title, author, etc.)
8. Write atomically:

```sql
UPDATE documents SET
  canonical_text = $1,
  canonical_hash = $2,
  text_byte_length = $3,
  extractor_version = $4,
  structure = $5,
  metadata = $6,
  status = 'ready',
  updated_at = NOW()
WHERE id = $7
RETURNING canonical_hash
```

9. If `canonical_hash` differs from previous value: enqueue `remap_highlights(document, old_hash, new_hash)`
10. Always enqueue `chunk_and_embed_document`

**Success postconditions**:

- `status = 'ready'`
- `canonical_text`, `structure`, `metadata` populated
- `hash` changed
- Downstream jobs enqueued

**Failure postconditions**:

- `status = 'failed'`
- `error_code = 'pdf_extraction_failed' | 'epub_parse_failed' | 'html_extraction_failed' | 'unknown_format'`
- `error_message` contains details

**Retry policy**:

- Max attempts: 5
- Backoff: 1m, 2m, 4m, 8m, 16m

---

### 2.3 Job: `chunk_and_embed_document`

**Purpose**: Chunk canonical text and generate embeddings for semantic search.

**Inputs**:

```typescript
{
  document_id: UUID,
  chunk_version: string,      // e.g., "v1"
  embedding_model: string     // e.g., "text-embedding-3-small"
}
```

**Preconditions**:

- Document has `status = 'ready'`
- `canonical_text` exists

**Idempotency key**:

```
(document_id, hash?, chunk_version, embedding_model)
```

If chunks already exist with these parameters, skip.

**Execution**:

1. Load document and canonical_text
2. Chunk document per [spec/embeddings.md](embeddings.md) §2.1
3. For each chunk:
   - Format embedding text (title, author, section, chunk text)
   - Call embedding API (e.g., OpenAI `text-embedding-3-small`)
   - Write to `content_chunks` table
4. Update document:

```sql
UPDATE documents SET
  embedding_status = 'ready',
  embedding_model = $1,
  chunk_version = $2,
  updated_at = NOW()
WHERE id = $3
```

**Success postconditions**:

- `embedding_status = 'ready'`
- Chunks in `content_chunks` table with embeddings
- Document searchable via retrieval

**Failure postconditions**:

- `embedding_status = 'failed'`
- `error_code = 'embedding_provider_timeout' | 'embedding_quota_exceeded' | 'chunking_failed' | 'text_too_long'`
- `error_message` contains details

**Retry policy**:

- Max attempts: 5
- Backoff: 2m, 4m, 8m, 16m, 32m

**Concurrency**: Chunk requests batched (up to 100 chunks per API call) to minimize embedding API calls.

---

### 2.4 Job: `remap_highlights`

See [spec/anchors.md](anchors.md) §3 for full specification.

Triggered when `hash` changes (document extracted with different extractor_version).

---

## 3. Phase 2+ Ingestion Jobs (Out of Scope)

The following jobs are enqueued in Phase 2 onwards and are OUT OF SCOPE for Phase 1:

- `ensure_episode_transcript` — ASR job for podcast/video transcription
- `refresh_podcast_feed` — Podcast RSS feed ingestion
- `chunk_and_embed_episode_transcript` — Chunking episodes/videos
- `chunk_and_embed_video_transcript` — Synonym for above

---

## 4. Document State Machine

**States**:

- `pending`: Created, ingestion not started
- `processing`: Extraction in progress
- `ready`: Canonical text available, chunks may still be embedding
- `failed`: Extraction failed

**Transitions**:

```
[create] → pending
pending → processing [ingest_document dequeued]
processing → ready [canonicalize_document success]
processing → failed [canonicalize_document max retries]
failed → pending [user retry or admin requeue]
ready → processing [re-extraction requested by admin]
```

**User-visible behavior**:

| State | UI Display |
|-------|------------|
| `pending` | "Processing..." spinner |
| `processing` | "Processing..." spinner |
| `ready` | Document readable (searchable once `embedding_status='ready'`) |
| `failed` | Error banner: "{error_message}. [Retry]" button |

---

## 5. Embedding State Machine

**States** (orthogonal to ingestion status):

- `pending`: Awaiting chunking/embedding
- `ready`: Embeddings in vector store, searchable
- `failed`: Embedding failed

**Transitions**:

```
[canonical_text ready] → pending
pending → ready [chunk_and_embed_document success]
pending → failed [chunk_and_embed_document max retries]
failed → pending [admin retry]
```

**User-visible behavior**:

| State | UI Display |
|-------|------------|
| `pending` | "Indexing for search..." (subtle note) |
| `ready` | No special indicator (search works) |
| `failed` | "Search unavailable for this document." |

---

## 6. Canonicalization Edge Cases

### 6.1 Large Documents

For documents > 5 MB:

- Streaming extraction to avoid memory overflow
- Chunks written to temporary file, then read into database
- Timeout: 5 minutes per document

### 6.2 Unsupported Formats

If format not recognized:

- Try PDF detection (pdfplumber)
- Try EPUB detection (zipfile + XML)
- Fallback to raw text extraction
- If all fail: `error_code = 'unknown_format'`

### 6.3 Scanned PDFs (No Text Layer)

If PDF has no text layer (scanned document):

- pdfplumber returns empty text
- Mark document `status='failed'` with `error_code='no_text_layer'`
- Recommend OCR (deferred to Phase 2)

### 6.4 Non-Latin Scripts

For non-Latin scripts (CJK, Arabic, etc.):

- pdfplumber handles basic extraction
- NFC normalization applied per CANON-2
- Segmentation algorithm may struggle (acceptable in v1)

---

## 7. Extraction Versioning Strategy

### 7.1 Tracking Extractor Changes

All extraction code is versioned:

```python
EXTRACTOR_VERSION = "2024.11.1"
```

When extractor code changes (bug fix, algorithm improvement):

1. Bump `EXTRACTOR_VERSION` (e.g., `2024.11.1` → `2024.11.2`)
2. Deploy new backend
3. Any new ingestions use new version
4. Highlights on old documents remain valid (different `hash` values)

### 7.2 Multi-Version Compatibility

Backend MUST support extracting from any recent version:

- 0-2 years back: fully supported
- 2-5 years back: supported with deprecation warning
- > 5 years: may be deprecated (Phase 3+)

This allows users to re-process old documents without losing highlights.

---

## 8. Error Handling & Retry Logic

### 8.1 Transient Errors

Errors that warrant retry (backoff + exponential jitter):

- S3 timeout, 503, 429
- Embedding API timeout, rate limit
- Database connection pool exhausted
- Temporary network error

### 8.2 Permanent Errors

Errors that warrant immediate failure (no retry):

- S3 file not found (404)
- Unknown document format
- PDF extraction catastrophic failure (corrupted file)
- Embedding API key invalid (401)

### 8.3 Dead-Letter Queue

After max retries, job moves to DLQ:

```json
{
  "original_job": { "name": "canonicalize_document", "data": {...} },
  "failure_reason": "pdf_extraction_failed: ...",
  "attempts": 5,
  "failed_at": "2024-11-25T10:30:00Z"
}
```

Admins review DLQ periodically and manually retry if appropriate.

---

## 9. Extracting Metadata

During canonicalization, the following metadata is extracted:

**For documents**:
- `title`: First heading or from PDF metadata
- `author`: From PDF metadata or HTML meta tags
- `published_date`: From HTML meta tags or user-provided
- `language`: Detected via langdetect (optional)

**For episodes** (Phase 2):
- `title`, `description`: From RSS feed or user-provided
- `published_date`: From RSS feed
- `duration`: Computed from audio blob or provided

**For videos** (Phase 2):
- `title`, `channel`: From YouTube/Vimeo API
- `published_date`: From platform
- `duration`: From video metadata

