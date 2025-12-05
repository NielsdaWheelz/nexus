# Nexus Subsystem Spec: Chunking, Search & Index

## 1. Scope

This subsystem handles all chunking of media text content, embedding generation, and search (semantic + keyword) for Nexus. It is responsible for decomposing `media.plain_text` into searchable chunks, generating and storing vector embeddings, building search indices, and answering search queries with strict visibility enforcement for social objects.

**In scope (v1):**

- Chunk model semantics: `media_id`, `chunking_strategy`, `sequence_index`, `content`, `embedding`, timestamps
- Chunking strategies (v1: single `tokens_v1` strategy with fixed parameters)
- Chunking jobs: deterministic decomposition of `media.plain_text` into Chunk rows
- Embedding generation: vector embeddings for all chunks using configured embedding model
- pgvector indexing: ANN (approximate nearest neighbor) index on `chunk.embedding`
- Keyword search indexing: tsvector/trigram indices on `media.plain_text`, `media.title`, `author.name`, `annotation.body`, `highlight.quote`
- Search HTTP API: one endpoint returning media with chunk hits and the viewer's own highlights/annotations (visibility-scoped)
- Search mode: single hybrid path (uses semantic when indexed; otherwise keyword)
- Search scoping: global or a single `media_id`
- Result ranking: combine semantic + keyword when both are available
- Visibility enforcement: all social object results must pass visibility rules (never leak private content)
- Graceful degradation: keyword-only per-media when semantic unavailable

**Explicitly out of scope (v1 non-goals):**

- Media ingestion, content fetching, PDF parsing (owned by ingestion subsystem)
- Canonical text extraction and highlight offset mapping (owned by canonical-text-highlights spec)
- Library creation/permissions logic (must call visibility rules, not implement them)
- LLM conversation generation
- Multi-mode toggles (`semantic_only`, `keyword_only`)
- Scopes beyond `media_id` (library, author, conversation)
- Search over messages/conversations or other people's social objects
- Custom ranking formulas, query expansion, personalization
- Chunking strategy selection UI; embedding model selection UI; re-ranking / weight tuning

## 2. Dependencies

### 2.1 Entities Read from Domain Model

This spec reads from (but does not write to):

- **Media:** `id`, `plain_text`, `title`, `processing_status`, `kind`, `canonical_url` (read-only)
- **Author:** `id`, `name` (read-only)
- **MediaAuthor:** `media_id`, `author_id` (read-only)
- **Library:** `id`, `name`, `owner_user_id`, `is_default` (read-only)
- **LibraryMedia:** `library_id`, `media_id` (read-only)
- **LibraryUser:** `library_id`, `user_id`, `role` (read-only)
- **User:** `id`, `email`, `display_name` (read-only for attribution)
- **Highlight:** `id`, `user_id`, `media_id`, `start_offset`, `end_offset`, `quote`, `created_at` (read-only)
- **Annotation:** `id`, `highlight_id`, `body`, `created_at` (read-only)
- (Conversations/messages are out of scope for v1 search)

### 2.2 Entities Written by This Subsystem

- **Chunk:** full lifecycle ownership (create, update, delete)
  - Fields: `id`, `media_id`, `chunking_strategy`, `sequence_index`, `content`, `embedding`, `created_at`
  - Write operations: insert chunk rows after `media.processing_status = 'ready_for_reading'`; update embeddings after generation; delete all chunks for (media, strategy) on retry
  - No other subsystem writes to `chunk` table

### 2.3 Dependencies on Other Specs

**From Ingestion Spec:**

- **Media state contract (ingestion-owned):**
  - `processing_status` enum (single source of truth): `pending`, `processing`, `ready_for_reading`, `indexed`, `failed`
  - Guarantee: `plain_text` is immutable after reaching `ready_for_reading`
  - Trigger point: chunking jobs enqueued when media reaches `ready_for_reading`
  - Chunk/search may only promote `ready_for_reading` → `indexed` after chunks+embeddings complete. On chunk/embedding failure, set `processing_status = 'failed'` with `failure_reason = 'indexing_failed'` and delete chunks; user may retry (failed → pending).
- **Empty plain_text handling (scanned PDFs):**
  - Media with `plain_text = ''` (scanned/image-only PDFs) reach `ready_for_reading` but never `indexed`
  - This subsystem MUST NOT enqueue chunking jobs for media with empty `plain_text`
  - Search MUST NOT return semantic results for media with `processing_status != 'indexed'`
  - Keyword search MUST still match over non-empty fields (e.g., `media.title`, `author.name`) even when `plain_text` is empty

**From Libraries/Permissions/Visibility Spec:**

- **Visibility rule (authoritative):**
  ```
  can_see_social_object(viewer, owner, media) ⟺ (viewer = owner) ∨ (∃ library L: viewer ∈ L ∧ owner ∈ L ∧ media ∈ L)
  ```
  - This subsystem MUST call `can_user_see_social_object(viewer_user_id, owner_user_id, media_id)` or equivalent SQL for all social object results
  - This subsystem MUST NOT implement its own visibility logic
  - Media is globally readable; only social objects are visibility-scoped
- **Visibility functions:**
  - `can_user_see_social_object(viewer_user_id, owner_user_id, media_id) -> bool`
  - `get_visible_social_object_owners_for_media(viewer_user_id, media_id) -> List[user_id]`
  - These functions are defined in libraries spec; this subsystem calls them

**From Canonical Text & Highlights Spec:**

- **Plain text contract:**
  - `media.plain_text` is the canonical linear text representation
  - All offsets, chunking, and search operate over `plain_text` only
  - Highlight offsets are 0-indexed character positions into `plain_text`
- **Highlight/annotation schema:**
  - Highlights store: `user_id`, `media_id`, `start_offset`, `end_offset`, `quote`, `created_at`
  - Annotations store: `highlight_id`, `body`, `created_at`
  - Visibility derived via shared library rule (no `library_id` on highlights/annotations)

### 2.4 External Services

- **pgvector extension:** for `chunk.embedding` storage and ANN queries
  - Required for semantic search
  - Index type: HNSW or IVFFlat (configured externally; v1 default: HNSW with `m=16`, `ef_construction=64`)
  - Distance metric: cosine (configured externally; v1 default)
- **PostgreSQL full-text search:** tsvector/tsquery for keyword search
  - GIN indices on text fields
  - Optionally: pg_trgm for trigram similarity (fuzzy matching)
- **Embedding API:** OpenAI-compatible endpoint (v1 pinned: OpenAI `text-embedding-3-small`, 1536d)
  - Interface: `generate_embeddings(texts: List[str]) -> List[np.ndarray]`
  - Deterministic: same input → same output
  - Rate limiting handled internally (exponential backoff)
- **Celery task queue:** for asynchronous chunking and embedding jobs
  - Idempotency: tasks check state before executing
  - Retry behavior: infrastructure failures retried by Celery (max 3 attempts); domain failures write `failed` status without retry

### 2.5 Critical Constraint: No Silent Visibility Leaks

**Invariant:** No endpoint or job can "accidentally" leak social objects that should be hidden by visibility rules.

**Enforcement:**
- All social object queries MUST join with visibility check (shared library intersection)
- No client-side filtering; all visibility checks server-side
- No caching of social object results without visibility context
- Search results MUST be filtered per-request based on `viewer_user_id`

## 3. Responsibilities

### 3.1 Must Do

1. **Chunking:**
   - Create Chunk rows for each `(media_id, chunking_strategy)` once media reaches `ready_for_reading`
   - Ensure "all or nothing" chunk sets per (media, strategy): either zero chunks or complete consistent set
   - Validate chunk invariants: sequence_index is 0-indexed, sequential, gap-free
   - Handle re-chunking: delete old chunks for (media, strategy) before inserting new chunks (atomic transaction)

2. **Embedding:**
   - Generate embeddings for all chunks via embedding API interface
   - Store embeddings as pgvector type in `chunk.embedding` column
   - Build pgvector ANN index (HNSW or IVFFlat) for semantic search
   - Transition `media.processing_status = 'indexed'` after all chunks have embeddings; failures set `processing_status = 'failed'` with `failure_reason = 'indexing_failed'`

3. **Search Indexing:**
   - Build keyword search indices (tsvector/trigram) on:
     - `media.plain_text` (or derived tsvector for performance)
     - `media.title`
     - `author.name`
     - `annotation.body`
     - `highlight.quote`
   - Indices MUST be updated automatically on insert/update (via PostgreSQL triggers or application logic)

4. **Search Queries:**
   - Provide unified search API: `POST /api/v1/search`
   - Single hybrid mode: semantic when indexed, otherwise keyword fallback per media
   - Optional scope: `media_id` only
   - Result types: media (with chunk hits) and the viewer's own highlights/annotations (visibility-scoped)
   - Combine semantic + keyword scores when both are available
   - Enforce visibility rules for all social object results

5. **Graceful Degradation:**
   - Semantic search MUST only use chunks for media with `processing_status = 'indexed'`
   - Keyword search MUST consider media where `processing_status ∈ {ready_for_reading, indexed}` when any indexed field is non-empty (title/author/plain_text/etc.)
   - If media are not indexed or embedding fails: return keyword-only for those media; do not drop them from search

6. **Visibility Enforcement:**
   - Media results: globally readable (all matching media returned)
   - Social object results: MUST pass visibility check (`viewer = owner` OR shared-library-with-media)
   - NEVER return social objects invisible to viewer
   - Use batch visibility checks (get all visible owner_ids for media) for performance

### 3.2 Must Not Do

1. **Authentication:** Do not perform authentication beyond extracting `current_user_id` from session/JWT
2. **Media Creation:** Do not create, modify, or delete Media rows (ingestion subsystem responsibility)
3. **LLM Calls:** Do not call LLMs for query expansion, relevance feedback, or summarization (future feature)
4. **Visibility Logic:** Do not implement visibility rules; call functions defined in libraries spec
5. **Plain Text Mutation:** Do not modify `media.plain_text` (immutable after `ready_for_reading`)
6. **Highlight/Annotation Storage:** Do not create/modify/delete highlights or annotations (respective subsystems)

## 4. External Interfaces

### 4.1 HTTP Endpoints

All endpoints require authentication. `current_user_id` is extracted from session/JWT.

---

#### POST /api/v1/search

**Purpose:** Unified search over media plus the viewer's own social objects (highlights/annotations).

**Request (v1):**
```json
{
  "query": "neural networks",
  "scope": {"media_id": "uuid"},
  "type_filters": ["media", "highlight", "annotation"],
  "limit": 50,
  "cursor": "base64-encoded-cursor"
}
```

**Fields:**
- `query` (required, string, max 500 chars)
- `scope` (optional): `{ "media_id": "uuid" }` only
- `type_filters` (optional): subset of `media`, `highlight`, `annotation` (default: all three); may be omitted in v1
- `limit` (optional, int; default 20, max 100)
- `cursor` (optional, string): pagination cursor

**Response (200 OK):**
```json
{
  "results": {
    "media": [
      {
        "media_id": "uuid",
        "title": "Introduction to Neural Networks",
        "authors": [{"id": "uuid", "name": "Geoffrey Hinton"}],
        "processing_status": "indexed",
        "chunk_hits": [
          {
            "chunk_id": "uuid",
            "sequence_index": 5,
            "snippet": "...neural networks learn by adjusting weights...",
            "score": 0.87,
            "search_mode_used": "hybrid"
          }
        ],
        "score": 0.87
      }
    ],
    "highlights": [...viewer-owned...],
    "annotations": [...viewer-owned...]
  },
  "cursor": "next-page-cursor-base64",
  "has_more": true,
  "query_info": {
    "mode_used": "hybrid",
    "semantic_available": true
  }
}
```

**Behavior (v1):**

1. Validate: `query` non-empty ≤500 chars; `limit` ≤100; `type_filters` subset of allowed; if `scope.media_id` is set, ensure media exists.
2. Resolve scope: if `media_id` present, restrict search to that media; otherwise global.
3. Execute hybrid search:
   - For media with `processing_status='indexed'`: run semantic (pgvector on chunks) + keyword; combine scores (fixed weights, implementation-defined).
   - For media with `processing_status ∈ {'ready_for_reading','failed'}`: keyword only.
   - Keyword search fields: `media.plain_text`, `media.title`, `author.name`, `annotation.body`, `highlight.quote` (and any other non-empty indexed fields). If `plain_text=''`, still match on title/author.
4. Social objects (v1): return only the viewer's own highlights/annotations when type-filtered in. Enforce visibility rule: viewer must be owner, or share a library containing the media; media are globally readable.
5. Pagination: cursor encodes last score+id; fetch `limit+1`; set `has_more`/`cursor` accordingly.
6. Timeouts: 30s hard timeout; may return partial results with a flag.

**Error Codes (v1):**
- `400 SEARCH_INVALID_QUERY`: empty/too long/malformed query
- `400 SEARCH_INVALID_TYPE_FILTER`: invalid type_filters value
- `404 SEARCH_SCOPE_NOT_FOUND`: media_id not found
- `500 SEARCH_TIMEOUT`: search exceeded timeout
- `500 INTERNAL_ERROR`: unexpected server error

**Note:** Additional modes/scopes/types (library/author/conversation, messages/conversations, other users' social objects) are future work, not v1.

---

#### GET /api/v1/media/{media_id}/search (optional alias)

Alias for `POST /api/v1/search` with `scope.media_id` set; same behavior and visibility.

---

### 4.2 Background Jobs

#### Task: `chunk_media_task(media_id, chunking_strategy='tokens_v1')`

**Purpose:** Chunk `media.plain_text` into Chunk rows using specified strategy.

**Trigger:** Enqueued by ingestion subsystem after media reaches `ready_for_reading`.

**Preconditions:**
- `media.processing_status = 'ready_for_reading'`
- `media.plain_text` is non-empty
- No existing chunks for `(media_id, chunking_strategy)` OR this is a retry

**Behavior:**

1. **State Check (Idempotency Guard):**
   - Begin transaction with `SELECT FOR UPDATE` on `media` row
   - If `processing_status != 'ready_for_reading'`: abort (already indexed or failed)
   - If `plain_text` is empty: abort (no text to chunk; media remains `ready_for_reading`)
   - Commit transaction (release lock)

2. **Retrieve Plain Text:**
   - Query `media.plain_text` (immutable at this point)

3. **Chunking:**
   - **v1 Strategy: `tokens_v1`**
     - Algorithm: Recursive character text splitter (langchain-compatible)
     - Parameters (fixed; configurable via env):
       - `chunk_size`: 1000 characters (approximate; may vary by ±10% based on sentence boundaries)
       - `chunk_overlap`: 200 characters (overlap between consecutive chunks)
       - `separators`: `["\n\n", "\n", ". ", " ", ""]` (try splits in order)
     - Determinism: Same `plain_text` → same chunks (given fixed parameters)
   - Call chunking interface: `chunk_text(plain_text, strategy_config) -> List[(sequence_index, content)]`
   - Validate output:
     - `sequence_index` is 0-indexed, sequential, no gaps: `[0, 1, 2, ..., N-1]`
     - Each `content` is non-empty string
     - Total chunks <= 10,000 (sanity limit; if exceeded, fail with `CHUNKING_ERROR`)

4. **Atomic Chunk Insertion:**
   - Within transaction:
     - Delete existing chunks: `DELETE FROM chunk WHERE media_id = :media_id AND chunking_strategy = :strategy`
     - Insert new chunks: `INSERT INTO chunk (media_id, chunking_strategy, sequence_index, content, embedding) VALUES ...` (embedding = NULL)
     - Commit transaction
   - Ensures atomicity: either zero chunks or complete chunk set for (media, strategy)

5. **Enqueue Embedding Job:**
   - After commit: enqueue `embed_chunks_task(media_id, chunking_strategy)`
   - Idempotent: if already enqueued, skip

6. **Logging:**
   - Emit log: `{"event": "media_chunking_complete", "media_id": "...", "strategy": "...", "chunk_count": N, "duration_ms": ...}`

**Failure Handling:**

- On exception during chunking or validation:
  1. Begin transaction
  2. Delete partial chunks (if any): `DELETE FROM chunk WHERE media_id = :media_id AND chunking_strategy = :strategy`
  3. Update `media.processing_status = 'failed'`, `failure_reason = 'indexing_failed'`
  4. Commit transaction
- Emit log: `{"event": "media_chunking_failed", "media_id": "...", "strategy": "...", "error": "...", "plain_text_length": N}`
- Domain-level failures are NOT automatically retried (requires manual retry via ingestion subsystem)
- Infrastructure failures (Celery broker errors) are retried by Celery (max 3 attempts)

**Atomicity Constraint:**
- For `(media_id, chunking_strategy)`: either zero chunks exist, or a complete consistent chunk set exists
- No partial chunk sets allowed (enforced by delete-then-insert within transaction)

**Transaction Boundaries:**
- Chunk insertion: atomic delete-then-insert within transaction
- Failure write: atomic status update
- Isolation level: READ COMMITTED

---

#### Task: `embed_chunks_task(media_id, chunking_strategy='tokens_v1')`

**Purpose:** Generate embeddings for all chunks of a given strategy.

**Trigger:** Enqueued after chunking completes for a strategy.

**Preconditions:**
- Chunks exist for `(media_id, chunking_strategy)` with `embedding IS NULL`
- `media.processing_status = 'ready_for_reading'`

**Behavior:**

1. **State Check:**
   - Query chunks: `SELECT id, content FROM chunk WHERE media_id = :media_id AND chunking_strategy = :strategy AND embedding IS NULL ORDER BY sequence_index`
   - If no chunks found: abort (idempotency guard; already embedded or chunking failed)

2. **Batch Embedding:**
   - Batch size: 100 chunks per API call (configurable; tuned for embedding API rate limits)
   - For each batch:
     - Extract `content` strings
     - Call embedding API: `generate_embeddings(texts) -> List[np.ndarray]`
       - v1 model: OpenAI `text-embedding-3-small`, 1536 dimensions
       - Deterministic: same input → same output
       - Rate limiting handled internally (exponential backoff)
     - Validate output: all embeddings have dimension 1536
     - Within transaction:
       - Update chunks: `UPDATE chunk SET embedding = :vector WHERE id = :chunk_id`
       - Commit transaction (per-batch commit for progress persistence)

3. **Verify Completion:**
   - Query: `SELECT COUNT(*) FROM chunk WHERE media_id = :media_id AND chunking_strategy = :strategy AND embedding IS NULL`
   - If count > 0: log error and fail (should not happen; all chunks should have embeddings)

4. **Update Media Status:**
   - Within transaction:
     - Update `media.processing_status = 'indexed'`, `processing_completed_at = NOW()`
     - Commit transaction
   - **Invariant:** Media transitions to `indexed` if and only if ALL chunks for (media, strategy) have `embedding IS NOT NULL`

5. **Logging:**
   - Emit log: `{"event": "media_embedding_complete", "media_id": "...", "strategy": "...", "chunk_count": N, "duration_ms": ...}`

**Failure Handling:**

- On exception during embedding:
  1. Begin transaction
  2. Delete all chunks and embeddings: `DELETE FROM chunk WHERE media_id = :media_id AND chunking_strategy = :strategy`
  3. Update `media.processing_status = 'failed'`, `failure_reason = 'indexing_failed'`
  4. Commit transaction
- Emit log: `{"event": "media_embedding_failed", "media_id": "...", "strategy": "...", "error": "...", "chunk_count": N}`
- Domain-level failures are NOT automatically retried
- Infrastructure failures are retried by Celery (max 3 attempts)

**Idempotency:**
- Embedding API is deterministic (same input → same output)
- Task can be retried; skips chunks with existing embeddings
- Partial progress is preserved (per-batch commits)

**Transaction Boundaries:**
- Per-batch embedding update: atomic within transaction
- Final status transition to `indexed`: atomic update
- Isolation level: READ COMMITTED

---

### 4.3 Events / Internal APIs

**v1 Implementation:**
This subsystem does not emit application-level events. Other subsystems poll database tables or call search endpoints directly.

**Future Extension (v2+):**
Post-v1 may add events for:
- `media.indexed` → cache warmup, analytics
- `search.query_executed` → usage tracking, query log analysis

**Internal API Contract (read-only database access):**

Other subsystems (reader, highlights, LLM conversations) may:
- Query `chunk` table for specific media chunks (ordered by `sequence_index`)
- Query `media` table for `processing_status` to determine search availability
- Call `POST /api/v1/search` endpoint with appropriate scope/filters

Constraints:
- Writes to `chunk` table are restricted to this subsystem only
- Writes to `media.processing_status` for `indexed` transition are restricted to this subsystem only
- Other subsystems MUST NOT modify search indices directly

---

## 5. State & Lifecycles

### 5.1 Chunk Lifecycle

**States:**
- `chunked_without_embeddings`: Chunk rows exist with `embedding IS NULL`
- `chunked_and_embedded`: Chunk rows exist with `embedding IS NOT NULL`
- `no_chunks`: No chunk rows exist for (media, strategy)

**State Transitions:**

```
┌──────────┐
│no_chunks │  Initial state (or after delete)
└────┬─────┘
     │
     │ chunk_media_task succeeds
     ▼
┌───────────────────────────┐
│chunked_without_embeddings │  Chunks exist, embeddings NULL
└────────┬──────────────────┘
         │
         │ embed_chunks_task succeeds
         ▼
┌────────────────────┐
│chunked_and_embedded│  Chunks exist, embeddings populated
└────────────────────┘  (terminal state for this strategy)
```

**Forbidden Transitions:**
- `chunked_and_embedded` → `chunked_without_embeddings` (embeddings are immutable once set)
- Direct transition `no_chunks` → `chunked_and_embedded` (must go through intermediate state)

**Re-chunking:**
- Trigger: Manual retry or strategy change (v2+)
- Behavior: Delete all chunks for (media, strategy), transition to `no_chunks`, re-run chunking
- Consequence: Embeddings are also deleted (cascade)

### 5.2 Media Search Status Lifecycle

**States (single enum, ingestion-owned `processing_status`):**
- `pending`: not started
- `processing`: extraction in progress
- `ready_for_reading`: extraction done; keyword search available if indexed fields exist
- `indexed`: chunking+embedding complete; semantic + keyword available
- `failed`: extraction or indexing failure (with `failure_reason`)

**Behavior:**
- Chunk/search may only promote `ready_for_reading` → `indexed` after all chunks have embeddings.
- Chunk/embedding failures set `processing_status = 'failed'`, `failure_reason = 'indexing_failed'`, delete chunks; user can retry (failed → pending).
- Semantic search only uses media in `indexed`.
- Keyword search uses media in `ready_for_reading`, `indexed`, or `failed` when at least one indexed field is non-empty (title, author, plain_text, highlight/annotation text).
- Media with `plain_text=''` skip chunking/embedding (semantic unavailable) but remain keyword-searchable via title/author.

---

## 6. Invariants (Local)

### 6.1 Chunk Invariants

1. **Atomicity:** For each `(media_id, chunking_strategy)`, either zero chunks exist, or a complete consistent chunk set exists. No partial chunk sets allowed.

2. **Sequence Ordering:** `sequence_index` MUST be 0-indexed, sequential, and gap-free for each `(media_id, chunking_strategy)`.
   - Valid: `[0, 1, 2, 3]`
   - Invalid: `[0, 1, 3, 4]` (gap at 2)

3. **Uniqueness:** `(media_id, chunking_strategy, sequence_index)` is unique (enforced by database constraint).

4. **Embedding Nullability:**
   - `embedding` MAY be NULL after chunking
   - `embedding` MUST be non-NULL after embedding task completes
   - NULL embeddings indicate incomplete indexing

5. **Embedding Dimension:** All embeddings MUST have dimension 1536 (v1 default; configurable via env).

6. **Content Non-Empty:** `chunk.content` MUST be non-empty string. Empty chunks forbidden.

7. **Media Reference:** `chunk.media_id` MUST reference a valid `media.id` where `plain_text` is non-empty.

8. **Strategy Validity:** `chunking_strategy` MUST be valid enum value (v1: only `tokens_v1` allowed).

9. **Re-chunking Safety:** Re-chunking for a given `(media_id, chunking_strategy)` MUST delete all existing chunks for that pair before inserting new chunks (atomic transaction).

### 6.2 Search Behavior Invariants

1. **Semantic Search Media Filter:**
   - Semantic search MUST only use chunks for media with `processing_status = 'indexed'`.

2. **Keyword Search Media Filter:**
   - Keyword search MUST consider media where `processing_status ∈ {ready_for_reading, indexed, failed}` when at least one indexed field is non-empty (title, author, plain_text, annotation.body, highlight.quote).
   - Media with `processing_status ∈ {pending, processing}` are excluded. `failed` indicates extraction or indexing failure; keyword search MAY still match if text/title exist.

3. **Empty Plain Text Handling:**
   - Media with `plain_text = ''` (scanned PDFs) MUST NOT appear in semantic search (no chunks).
   - Keyword search MUST still match such media via other indexed fields (e.g., title/author).

4. **Visibility Enforcement (Critical):**
   - Search MUST NEVER return highlights/annotations that violate visibility rules.
   - Visibility rule: viewer can see a social object iff viewer=owner OR viewer and owner share a library that contains the referenced media. Implement server-side, per-request, using current LibraryUser/LibraryMedia state.

5. **Result Type Segregation:**
   - Media results: globally readable (no visibility filter)
   - Social object results: visibility-scoped
   - Results MUST be grouped by type in response

6. **Score Normalization:**
   - All scores MUST be normalized to [0, 1] range when combining semantic+keyword

7. **Pagination Stability:**
   - Cursor-based pagination MUST be stable across concurrent writes
   - Cursor encodes: last result's score + id (deterministic ordering)

### 6.3 Invariants on Plain Text Mutation

1. **Immutability:**
   - `media.plain_text` MUST NOT be modified after `processing_status` reaches `ready_for_reading`
   - Any attempt to modify `plain_text` after this point MUST fail (constraint violation or application error)

2. **Chunk Derivation:**
   - All chunks for a media MUST be derived from the immutable `plain_text`
   - Re-chunking (if needed) operates over the same immutable `plain_text`

3. **Highlight Compatibility:**
   - Chunks MUST NOT mutate `plain_text` (highlights depend on stable offsets)
   - Chunking operates over `plain_text` as read-only input

---

## 7. Error Handling

### 7.1 Search API Error Codes (v1)

| Error Code                   | HTTP Status | Meaning                                           | User Action           |
|------------------------------|-------------|---------------------------------------------------|-----------------------|
| `SEARCH_INVALID_QUERY`       | 400         | Query is empty, too long (>500 chars), malformed  | Provide valid query   |
| `SEARCH_INVALID_TYPE_FILTER` | 400         | type_filters contains invalid value               | Use valid type filter |
| `SEARCH_SCOPE_NOT_FOUND`     | 404         | Requested media_id does not exist                 | Verify media_id       |
| `SEARCH_TIMEOUT`             | 500         | Search exceeded timeout (30s)                     | Retry or refine query |
| `INTERNAL_ERROR`             | 500         | Unexpected server error                           | Retry or contact support |

### 7.2 Background Job Error Codes (stored in `failure_reason`)

| Error Code          | Cause                                        | Retry Behavior                          |
|---------------------|----------------------------------------------|-----------------------------------------|
| `CHUNKING_ERROR`    | Chunking logic crashed or validation failed  | Safe to retry (likely transient)        |
| `EMBEDDING_ERROR`   | Embedding API failed (timeout, rate limit)   | Safe to retry (transient API issue)     |

### 7.3 Error Handling Behavior

**Search Timeouts:**
- Hard timeout: 30s per search request
- If timeout reached:
  - Return partial results (if any)
  - Set `query_info.partial_results: true` in response
  - Log timeout event for monitoring

**Partial Semantic Availability:**
- If user searches and some media are `ready_for_reading` (keyword-only) while others are `indexed` (semantic+keyword):
  - Execute hybrid search on indexed media
  - Execute keyword search on ready_for_reading media
  - Merge results
  - Annotate each result with `search_mode_used` field
  - Do NOT block entire search; degrade gracefully per-media

**Embedding API Failures:**
- On rate limit (429): exponential backoff (2s, 4s, 8s, 16s, 32s)
- On timeout (>30s): fail batch, retry up to 3 times (Celery automatic retry)
- On 5xx error: fail batch, retry up to 3 times
- On 4xx error (except 429): fail immediately, write `EMBEDDING_ERROR` (likely permanent)

---

## 8. Performance, Limits, Pagination

### 8.1 Query Limits

| Limit Type               | Value          | Rationale                                      |
|--------------------------|----------------|------------------------------------------------|
| Max query length         | 500 chars      | Prevent abuse; typical queries < 100 chars     |
| Default page size        | 20 results     | Balanced load/UX                               |
| Max page size            | 100 results    | Prevent excessive load                         |
| Search timeout           | 30s            | Balance UX (user patience) vs load             |

### 8.2 Database Indices

**Required Indices:**

1. **Chunk Table:**
   - Primary key: `(id)`
   - Unique constraint: `(media_id, chunking_strategy, sequence_index)`
   - pgvector index: `chunk.embedding` (HNSW with m=16, ef_construction=64; cosine distance)
   - B-tree index: `(media_id, chunking_strategy)` for chunk retrieval

2. **Media Table (for search):**
   - tsvector index (GIN): `to_tsvector('english', coalesce(title, '') || ' ' || coalesce(plain_text, ''))`
   - B-tree index: `(processing_status)` for filtering
   - Optionally: trigram index (pg_trgm) on `title` for fuzzy matching

3. **Author Table:**
   - tsvector index (GIN): `to_tsvector('english', name)`

4. **Highlight Table:**
   - tsvector index (GIN): `to_tsvector('english', quote)`
   - B-tree index: `(media_id, user_id)` for visibility checks

5. **Annotation Table:**
   - tsvector index (GIN): `to_tsvector('english', body)`
   - B-tree index: `(highlight_id)` for joins

6. **LibraryMedia / LibraryUser (for visibility):**
   - Composite index: `(library_id, media_id)` on LibraryMedia
   - Composite index: `(library_id, user_id)` on LibraryUser
   - These enable fast shared library intersection queries

### 8.3 Expected Performance

| Operation                        | Target (p95)   | Notes                                      |
|----------------------------------|----------------|--------------------------------------------|
| Semantic search (single media)   | < 200ms        | ANN query on chunks                        |
| Keyword search (global)          | < 500ms        | Full-text search on tsvector indices       |
| Hybrid search (global)           | < 500ms        | Parallel semantic + keyword, then merge    |
| Visibility check (per result)    | < 10ms         | Indexed join on LibraryMedia/LibraryUser   |
| Chunk retrieval (single media)   | < 50ms         | B-tree lookup by (media_id, strategy)      |
| Embedding generation (100 chunks)| < 5s           | Dependent on embedding API latency         |

### 8.4 Pagination

**Cursor-Based Pagination (v1):**
- Cursor format: base64-encoded `{"score": 0.87, "id": "uuid", "type": "media"}`
- Ordering: score DESC, id DESC (deterministic secondary sort)
- Fetch `limit + 1` results; if more exist, generate cursor for next page
- Stability: concurrent writes may cause duplicates/skips (acceptable for v1)

**Offset Pagination Issues (NOT used in v1):**
- Concurrent inserts can cause duplicate results across pages
- Offset skipping is inefficient at large offsets

**Example (v1):**
```
POST /api/v1/search
{
  "query": "neural networks",
  "limit": 20,
  "cursor": null
}

Response:
{
  "results": { ... },
  "cursor": "eyJzY29yZSI6MC44NywgImlkIjogInV1aWQiLCAidHlwZSI6ICJtZWRpYSJ9",
  "has_more": true
}

Next page:
POST /api/v1/search
{
  "query": "neural networks",
  "limit": 20,
  "cursor": "eyJzY29yZSI6MC44NywgImlkIjogInV1aWQiLCAidHlwZSI6ICJtZWRpYSJ9"
}
```

### 8.5 Scalability Targets (v1)

- **Corpus size:** Up to 10,000 media per user (free tier: 5; personal/pro: unlimited)
- **Chunk count:** Up to 100 million chunks total (10,000 media × 10,000 chunks avg)
- **Concurrent searches:** 100 req/s (with proper indexing and caching)
- **Embedding API rate limits:** 100,000 tokens/min (configurable; provider-dependent)

**Note:** Specific SLOs are deployment-specific and should be tuned based on observed production performance.

---

## 9. Observability (minimal)

- Logs (required): chunking/embedding start, success, failure (media_id, strategy, chunk_count, duration_ms, failure_reason); search requests (user_id, query, scope, mode_used, latency_ms, result_counts).
- Metrics (required, names illustrative): `search_latency_ms`, `search_queries_total`, `chunking_jobs_failed_total`, `embedding_jobs_failed_total`.
- Dashboards/backoff/admin endpoints belong in ops/implementation docs; not specified in this spec.

## 10. Tests (v1 minimum)

- Chunk media (tokens_v1): sequential indices; atomic delete+insert; re-chunk replaces prior set.
- Chunk media with `plain_text=''`: job skipped; no chunks created.
- Embed chunks success: fills embeddings and promotes `ready_for_reading` → `indexed`.
- Embed failure: deletes chunks, sets `processing_status='failed'` with `failure_reason='indexing_failed'`; keyword search still works if text/title exist.
- Search hybrid: media results with chunk snippets when indexed; keyword fallback when not indexed; respects type_filters.
- Scanned PDF: semantic excluded; keyword can find by title/author.
- Visibility: highlights/annotations only when viewer=owner or shared-library-with-media; media always global.
- Pagination: cursor returns deterministic next page.

---

## 11. Open Questions

### 11.1 Resolved (v1 Decisions)

1. **Q:** What chunking strategy should we use?
   **A:** v1 uses single strategy `tokens_v1` (recursive character splitter, chunk_size=1000, overlap=200). Multi-strategy support deferred to v2+.

2. **Q:** What embedding model should we use?
   **A:** v1 uses OpenAI `text-embedding-3-small`, 1536 dimensions. Model selection UI deferred to v2+.

3. **Q:** How do we combine semantic + keyword scores in hybrid mode?
   **A:** v1 uses fixed weights: `0.6 * semantic_score + 0.4 * keyword_score`. Weight tuning deferred to v2+.

4. **Q:** How do we handle empty `plain_text` (scanned PDFs)?
   **A:** Do not enqueue chunking; media remains `ready_for_reading`; excluded from semantic search; keyword search still works via title/author.

5. **Q:** What is the maximum chunk count per media?
   **A:** v1 sanity limit: 10,000 chunks per media. If exceeded, fail with `CHUNKING_ERROR`.

### 11.2 Open (Non-Blocking; Can Be Decided During Implementation)

1. **Q:** Should we support query expansion or query rewriting?
   **A:** OUT OF SCOPE for v1. Future extension: use LLM to expand queries, extract entities, etc.

2. **Q:** Should we support filtering by date range or media kind in search?
   **A:** OUT OF SCOPE for v1. Future extension: add `filters: {kind, date_range, ...}` to search request.

3. **Q:** Should we support "more like this" search (find similar media)?
   **A:** OUT OF SCOPE for v1. Future extension: use media-level embeddings (average of chunk embeddings).

4. **Q:** Should we support personalized ranking (boosting media user frequently reads)?
   **A:** OUT OF SCOPE for v1. Future extension: add user interaction signals to ranking.

5. **Q:** Should we support multi-language search (non-English)?
   **A:** OUT OF SCOPE for v1. v1 assumes English text (tsvector uses 'english' config). Future extension: detect language, use appropriate config.

6. **Q:** Should we support search history or saved searches?
   **A:** OUT OF SCOPE for v1. Future feature: store user search queries for autocomplete, trending queries, etc.

---

## 12. Future Extensions

**Potential post-v1 enhancements:**

1. **Additional chunking strategies:**
   - `sections_v2`: Chunk by semantic sections (headers, paragraphs)
   - `semantic_spans`: Use NLP to identify semantic boundaries
   - Multi-strategy per media: allow multiple chunking strategies coexisting

2. **Advanced ranking:**
   - Personalized ranking: boost media user frequently reads/highlights
   - Recency boost: boost newer content in search results
   - Query expansion: use LLM to expand queries, extract entities
   - Re-ranking: use cross-encoder model for top-k results

3. **Precomputed media embeddings:**
   - Store single embedding per media (average of chunk embeddings)
   - Enable "find similar media" search
   - Faster media-level search (no chunk iteration)

4. **Multi-language support:**
   - Detect language, use appropriate tsvector config
   - Multi-language embedding models (OpenAI supports 100+ languages)

5. **Search filters:**
   - Filter by date range (created_at, updated_at)
   - Filter by media kind (html, epub, pdf)
   - Filter by author (already supported via scope; expose as filter)
   - Filter by library (already supported via scope; expose as filter)

6. **Search analytics:**
   - Track user search queries for trending topics, autocomplete
   - Track click-through rates (which results users click)
   - A/B test ranking formulas

7. **Search suggestions:**
   - Autocomplete based on previous queries
   - "Did you mean...?" spelling correction
   - Related searches ("People also searched for...")

8. **Highlight/annotation search enhancements:**
   - Search within own highlights/annotations only (already supported via `mine_only`)
   - Search by highlight color
   - Search by annotation creation date

10. **Performance optimizations:**
    - Cache frequent queries (with TTL and visibility context)
    - Precompute tsvector for `media.plain_text` (store in separate column)
    - Use approximate nearest neighbor (ANN) index tuning (adjust m, ef_construction for pgvector)

11. **Export search results:**
    - Export to CSV, JSON
    - Email search results
    - Save search as "smart library" (dynamic query)

12. **Search API v2:**
    - GraphQL endpoint (more flexible than REST)
    - Streaming results (SSE or WebSockets for real-time updates)

---

## End of Specification

**Status: IMPLEMENTATION-READY**

This document defines the complete interface contract and invariants for the chunking, search, and indexing subsystem. A competent engineer or LLM can now:

1. Implement all search & chunking endpoints and jobs
2. Design the database indexes (pgvector HNSW, GIN tsvector)
3. Write comprehensive tests (unit, integration, visibility)

**Critical Constraints (Must Obey):**

1. **Visibility:** No endpoint can leak social objects that should be hidden. All visibility checks MUST use shared library intersection rule from libraries spec.

2. **Chunk Atomicity:** For each (media, strategy), either zero chunks or complete chunk set. No partial sets.

3. **Plain Text Immutability:** Do not modify `media.plain_text` after `ready_for_reading`. Chunks derived from immutable text.

4. **Graceful Degradation:** Search MUST work even if semantic indexing incomplete (keyword fallback).

5. **Status Transitions:** Chunk/search may only promote `ready_for_reading` → `indexed` after chunks+embeddings complete; failures do not change `processing_status`.

**Open Questions:**
- All v1 questions resolved (§11.1)
- Non-blocking questions (§11.2) can be decided during implementation or deferred to v2+

**Post-Implementation Validation:**
- All invariants in §6 MUST be enforced by tests in §10
- All error codes in §7 MUST be covered by integration tests
- Visibility rule tests in §10.3 MUST pass (no leaked social objects)
- Performance targets in §8 SHOULD be met (measure and tune)

**Deviations from invariants are forbidden.** Ambiguities MUST be escalated to product owner.
