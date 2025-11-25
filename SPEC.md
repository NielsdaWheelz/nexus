# Reading-First Knowledge Management System: Production Specification

**Version**: 3.0
**Status**: Normative production specification
**Last Updated**: 2024-11-25

---

## 1. Scope and Definitions

### 1.1 System Definition

This specification defines a **reading-first knowledge management system** providing:

1. **Canonical text representation**: Deterministic transformation of unstructured content (PDF, EPUB, HTML, podcasts, videos) into immutable UTF-8 byte arrays with stable offsets
2. **Persistent text anchoring**: Highlight and annotation primitives that survive content re-ingestion through deterministic remapping
3. **Privacy-preserving retrieval**: Semantic search across heterogeneous content with mandatory visibility filtering
4. **Contextual conversation**: LLM-augmented chat with retrieval-assembled context respecting visibility boundaries

### 1.1.1 Architecture Overview

**Backend**: Single authoritative backend written in **Python/FastAPI**

- All canonicalization, ingestion, chunking, embedding, remapping logic executed server-side
- Highlight remapping orchestration
- LLM request processing and context assembly
- JWT verification via Clerk JWKS endpoint

**Database**: **PostgreSQL (Supabase) + pgvector** extension

- All persistent state, user data, media metadata
- Vector embeddings for semantic search
- Transactional consistency for highlight operations

**Job Queue**: **Redis + Celery** (or RQ/Huey)

- Document ingestion pipelines (canonicalization, chunking)
- Embedding generation jobs
- Highlight remap jobs (triggered on media version changes)
- Conversation summary jobs

**Frontends**: Web (React) and Mobile (React Native)

- **Web**: React with pdf.js for PDF selection and display, custom text readers for EPUB/web articles
- **Mobile**: React Native with WebView running pdf.js for PDFs, native views for EPUB/transcripts
- Both use identical anchor semantics (byte offsets for text media, pdf.js offsets for PDFs, time-aligned offsets for transcripts)
- Both authenticate via **Clerk SDKs**
- Both communicate with FastAPI via generated OpenAPI client (HTTP/JSON)

**Authentication**: **Clerk** (hosted OIDC provider)

- All user authentication flows delegate to Clerk
- Clerk SDKs handle login/logout on clients
- FastAPI verifies JWTs using Clerk's JWKS endpoint
- Backend verifies JWT signature and maps `sub` claim to `users.external_user_id`
- Never handles passwords (delegated to Clerk)

### 1.2 Normative Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

### 1.3 Out of Scope

The following are explicitly excluded from this specification:

- Full offline operation (optimistic UI for pending actions only)
- Multi-user collaborative editing
- Highlight version history
- First-class summary objects (summaries are conversation fields)
- Nested organizational structures (single-level libraries only)
- Workspace-level abstraction
- Anonymous access (all users must authenticate)

---

## 2. Media Types and Canonical Text

### 2.1 Media Type Classification

The system supports three primary media classes:

1. **Documents** (PDF, EPUB, web articles)
   - Extracted to linear canonical text via deterministic rules
   - Includes structure metadata (chapters, sections)
   - Highlights anchored via byte offsets in canonical text (or pdf.js offsets for PDFs)

2. **Episodes** (podcasts with optional transcripts)
   - Audio content with optional transcript text
   - Transcript may come from ASR (Whisper) or external service
   - Highlights anchored via byte offsets in transcript text + time ranges

3. **Videos** (YouTube, Vimeo, etc. with transcripts)
   - Video content with optional transcript text
   - Transcript may come from platform captions or ASR
   - Highlights anchored via byte offsets in transcript text + time ranges

Each media type has:

- Dedicated database table (`documents`, `episodes`, `videos`)
- Type-specific extraction rules (§2.2)
- Type-specific anchor semantics (§3.2)
- Type-specific ingestion jobs

### 2.2 Canonical Text and Versioning

**Canonical text** is a UTF-8 encoded byte array produced by a deterministic extraction function.

#### 2.2.1 Canonicalization Function

For documents, canonicalization is a pure function:

```
canonicalize: (raw_blob: bytes, extractor_version: string) → canonical_text: bytes
```

**Invariants**:

- **CANON-1**: `canonicalize(B, V)` MUST produce byte-identical output for identical inputs `(B, V)`
- **CANON-2**: Output MUST be valid UTF-8 with NFC normalization
- **CANON-3**: Output MUST NOT contain null bytes (`0x00`)
- **CANON-4**: Whitespace MUST be normalized: `\r\n → \n`, multiple spaces collapsed to single space, paragraph boundaries marked by exactly two `\n` characters

**Extraction environment**:

- Extractor code version MUST be pinned (e.g., `pdfplumber==0.10.3`, `pypdf==3.17.1`)
- Python runtime MUST be pinned (e.g., `python==3.11.6`)
- All dependencies MUST be locked via hash-verified requirements

#### 2.2.2 Document Extraction Rules

**PDF**:

1. Extract text using `pdfplumber` with `layout=True`
2. Remove headers/footers: discard text appearing identically on ≥3 consecutive pages
3. Remove page numbers: discard lines matching `^\s*\d+\s*$`
4. Preserve paragraph boundaries via double newline
5. Apply normalization per CANON-4

**EPUB**:

1. Parse spine order from `content.opf`
2. Extract text from XHTML documents in spine order
3. Convert block elements (`<p>`, `<div>`, `<h1>`..`<h6>`) to text with paragraph separators
4. Strip inline markup (`<em>`, `<strong>`, etc.)
5. Apply normalization

**HTML (web articles)**:

1. Apply Readability.js extraction
2. Extract `textContent` from article node (recursive, depth-first)
3. Strip `<script>`, `<style>`, `<nav>`, elements with `role="complementary"`
4. Apply normalization

#### 2.2.3 Transcript Extraction Rules

For transcripts (episodes, videos), canonicalization includes both text and time-alignment data:

```
transcribe: (audio_blob: bytes, asr_model_version: string, language_hint?: string)
          → (transcript_text: bytes, segments: Segment[])

Segment = {
  text_start: uint64,    // byte offset in transcript_text
  text_end: uint64,      // exclusive
  time_start: float64,   // seconds
  time_end: float64      // exclusive
}
```

**Invariants**:

- **TRANS-1**: Segments MUST be strictly ordered by `text_start` and `time_start`
- **TRANS-2**: Segments MUST partition `transcript_text` without gaps or overlaps:
  - `segments[0].text_start = 0`
  - `segments[i].text_end = segments[i+1].text_start` for all `i`
  - `segments[n-1].text_end = len(transcript_text)`
- **TRANS-3**: Time ranges MUST be strictly increasing: `segments[i].time_end ≤ segments[i+1].time_start`

**ASR normalization**:

1. Concatenate segment texts with single space separators
2. Apply CANON-4 normalization
3. Compute byte offsets for each segment in normalized text
4. Store as `transcript_segments` JSON array

**Non-determinism tolerance**:

ASR providers MAY produce different outputs for identical audio. This is tolerated via `transcript_hash` comparison (see §2.2.4).

### 2.2.4 Content Hashing and Versioning

#### 2.2.4.1 Hash Definitions

**`content_hash`** (documents):

```
content_hash = SHA256(raw_blob)
```

Identifies the raw input. Change detection: re-upload of identical file produces same hash.

**`canonical_hash`** (documents):

```
canonical_hash = SHA256(canonical_text)
```

Identifies the extracted text. Detects extraction code changes even if input unchanged.

**`transcript_hash`** (episodes, videos):

```
transcript_hash = SHA256(transcript_text)
```

Identifies transcript output. Detects ASR model changes or provider non-determinism.

#### 2.2.4.2 Version Fields

**Documents**:

- `content_hash: string` — SHA256 hex of raw blob
- `canonical_version: uint32` — monotonic counter, incremented when `canonical_text` changes
- `extractor_version: string` — semantic version of extraction code (e.g., `"2024.11.1"`)

**Episodes/Videos**:

- `transcript_hash: string` — SHA256 hex of `transcript_text`
- `asr_model_version: string` — model identifier (e.g., `"whisper-large-v3"`)

#### 2.2.4.3 Version Increment Rules

**`canonical_version` increment triggers**:

1. Re-ingestion of different `content_hash` (user uploaded new file version)
2. Change in `extractor_version` that produces different `canonical_hash` for same `content_hash`
3. Manual re-extraction by admin

**Effect**: All highlights referencing previous `canonical_version` become stale and MUST trigger remap job.

**`transcript_hash` change triggers**:

1. Re-transcription with different `asr_model_version`
2. ASR provider non-determinism (rare but tolerated)
3. Manual re-transcription by admin

**Effect**: All highlights referencing previous `transcript_hash` become stale and MUST trigger remap job.

### 2.3 Storage Schema

#### 2.3.1 Documents Table

```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  author TEXT,
  published_date DATE,
  source_url TEXT,

  -- Raw blob
  raw_blob_key TEXT NOT NULL,
  content_hash TEXT NOT NULL,

  -- Canonical text
  canonical_text TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,
  canonical_version INTEGER NOT NULL DEFAULT 1,
  text_byte_length INTEGER NOT NULL,
  extractor_version TEXT NOT NULL,

  -- Structure
  structure JSONB NOT NULL,

  -- Metadata
  metadata JSONB NOT NULL DEFAULT '{}',
  language TEXT,

  -- Status
  status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
  error_code TEXT,
  error_message TEXT,
  retries_count INTEGER NOT NULL DEFAULT 0,
  last_attempted_at TIMESTAMPTZ,

  -- Embedding status
  embedding_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (embedding_status IN ('pending', 'ready', 'failed')),
  embedding_model TEXT,
  chunk_version TEXT,

  -- Soft delete
  deleted_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_user ON documents(user_id);
CREATE INDEX idx_documents_status ON documents(status) WHERE status != 'ready' AND deleted_at IS NULL;
CREATE INDEX idx_documents_embedding_status ON documents(embedding_status) WHERE embedding_status != 'ready' AND deleted_at IS NULL;
CREATE INDEX idx_documents_content_hash ON documents(content_hash);
```

#### 2.3.2 Episodes Table

```sql
CREATE TABLE episodes (
  id UUID PRIMARY KEY,
  podcast_id UUID NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  published_date TIMESTAMPTZ,
  audio_url TEXT NOT NULL,
  duration_seconds FLOAT8,
  audio_blob_key TEXT,

  -- Transcript
  transcript_text TEXT,
  transcript_hash TEXT,
  transcript_segments JSONB,
  asr_model_version TEXT,

  -- Status
  transcript_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (transcript_status IN ('pending', 'processing', 'ready', 'failed')),
  transcript_error_code TEXT,
  transcript_error_message TEXT,
  transcript_retries_count INTEGER NOT NULL DEFAULT 0,
  transcript_last_attempted_at TIMESTAMPTZ,

  embedding_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (embedding_status IN ('pending', 'ready', 'failed')),
  embedding_model TEXT,
  chunk_version TEXT,

  metadata JSONB NOT NULL DEFAULT '{}',

  deleted_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_episodes_podcast ON episodes(podcast_id, published_date DESC);
CREATE INDEX idx_episodes_user ON episodes(user_id);
CREATE INDEX idx_episodes_transcript_status ON episodes(transcript_status) WHERE transcript_status != 'ready' AND deleted_at IS NULL;
```

#### 2.3.3 Videos Table

```sql
CREATE TABLE videos (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  channel TEXT,
  published_date TIMESTAMPTZ,
  source_url TEXT NOT NULL UNIQUE,
  duration_seconds FLOAT8,
  thumbnail_url TEXT,

  -- Transcript (same schema as episodes)
  transcript_text TEXT,
  transcript_hash TEXT,
  transcript_segments JSONB,
  asr_model_version TEXT,

  transcript_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (transcript_status IN ('pending', 'processing', 'ready', 'failed')),
  transcript_error_code TEXT,
  transcript_error_message TEXT,
  transcript_retries_count INTEGER NOT NULL DEFAULT 0,
  transcript_last_attempted_at TIMESTAMPTZ,

  embedding_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (embedding_status IN ('pending', 'ready', 'failed')),
  embedding_model TEXT,
  chunk_version TEXT,

  metadata JSONB NOT NULL DEFAULT '{}',

  deleted_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_videos_source_url ON videos(source_url);
CREATE INDEX idx_videos_user ON videos(user_id);
CREATE INDEX idx_videos_transcript_status ON videos(transcript_status) WHERE transcript_status != 'ready' AND deleted_at IS NULL;
```

#### 2.3.4 Users Table

```sql
CREATE TABLE users (
  id UUID PRIMARY KEY,
  external_user_id TEXT NOT NULL UNIQUE,  -- Clerk 'sub' claim
  email TEXT NOT NULL UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_external_user_id ON users(external_user_id);
```

---

## 3. Highlight Anchoring

### 3.1 Highlight Primitive

A **highlight** is a text span anchored to canonical text via byte offsets, with context for disambiguation.

#### 3.1.1 Highlight Schema

```sql
CREATE TABLE highlights (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  -- Media reference (polymorphic)
  media_type TEXT NOT NULL CHECK (media_type IN ('document', 'episode', 'video')),
  media_id UUID NOT NULL,

  -- Anchor type
  anchor_type TEXT NOT NULL CHECK (anchor_type IN ('text', 'pdf', 'transcript')),

  -- Byte offsets (immutable after creation)
  text_start BIGINT NOT NULL,
  text_end BIGINT NOT NULL CHECK (text_end > text_start),

  -- Anchoring data (immutable)
  quote TEXT NOT NULL,
  prefix TEXT NOT NULL,
  suffix TEXT NOT NULL,

  -- Version anchor (immutable)
  canonical_version INTEGER,
  transcript_hash TEXT,

  -- PDF-specific anchoring (for anchor_type='pdf')
  pdf_page_number INTEGER,
  pdf_char_offset INTEGER,
  pdf_extraction_confidence FLOAT4,
  pdf_file_hash TEXT,

  -- Transcript-specific anchoring (for anchor_type='transcript')
  time_start FLOAT8,
  time_end FLOAT8,

  -- Mutable fields
  color TEXT NOT NULL DEFAULT 'yellow'
    CHECK (color IN ('yellow', 'blue', 'green', 'pink', 'purple')),
  is_hidden BOOLEAN NOT NULL DEFAULT FALSE,

  -- Detachment state
  is_detached BOOLEAN NOT NULL DEFAULT FALSE,
  detached_reason TEXT,

  -- Visibility
  is_public BOOLEAN NOT NULL DEFAULT FALSE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT highlight_version_anchor CHECK (
    (media_type = 'document' AND canonical_version IS NOT NULL AND transcript_hash IS NULL) OR
    (media_type IN ('episode', 'video') AND transcript_hash IS NOT NULL AND canonical_version IS NULL)
  ),

  CONSTRAINT highlight_anchor_type_validity CHECK (
    (anchor_type = 'text' AND pdf_page_number IS NULL AND pdf_char_offset IS NULL AND pdf_extraction_confidence IS NULL AND pdf_file_hash IS NULL AND time_start IS NULL AND time_end IS NULL) OR
    (anchor_type = 'pdf' AND pdf_page_number IS NOT NULL AND pdf_char_offset IS NOT NULL AND pdf_file_hash IS NOT NULL AND time_start IS NULL AND time_end IS NULL) OR
    (anchor_type = 'transcript' AND time_start IS NOT NULL AND time_end IS NOT NULL AND pdf_page_number IS NULL AND pdf_char_offset IS NULL AND pdf_extraction_confidence IS NULL AND pdf_file_hash IS NULL)
  ),

  CONSTRAINT highlight_media_anchor_compatibility CHECK (
    (media_type = 'document' AND anchor_type IN ('text', 'pdf')) OR
    (media_type IN ('episode', 'video') AND anchor_type = 'transcript')
  )
);

CREATE INDEX idx_highlights_user ON highlights(user_id) WHERE NOT is_hidden;
CREATE INDEX idx_highlights_media ON highlights(media_type, media_id);
CREATE INDEX idx_highlights_anchor_type ON highlights(anchor_type);
CREATE INDEX idx_highlights_pdf ON highlights(media_id, pdf_page_number) WHERE anchor_type = 'pdf';
CREATE INDEX idx_highlights_transcript ON highlights(media_id, time_start) WHERE anchor_type = 'transcript';
```

#### 3.1.2 Anchor Type Details

Highlights use three distinct anchor types depending on media format and rendering requirements:

##### 3.1.2.1 Text Anchors (`anchor_type='text'`)

Used for: EPUB documents, web articles, and any canonical text media where byte offsets are stable.

**`text_start`, `text_end`**:

- Zero-indexed byte positions in `canonical_text` (UTF-8 encoding)
- `[start, end)` interval (inclusive start, exclusive end)
- MUST satisfy: `0 ≤ text_start < text_end ≤ len(canonical_text)`

**`quote`**:

- The exact bytes `canonical_text[text_start:text_end]` at creation time
- Maximum length: 10,000 bytes
- MUST be validated at creation: `quote = canonical_text[text_start:text_end]`

**`prefix`**:

- Context before quote: `canonical_text[max(0, text_start - 64):text_start]`
- Fixed length: `P = 64` bytes
- If `text_start < 64`, prefix is truncated

**`suffix`**:

- Context after quote: `canonical_text[text_end:min(len(canonical_text), text_end + 64)]`
- Fixed length: `S = 64` bytes
- If `text_end + 64 > len(canonical_text)`, suffix is truncated

**Type-specific fields**: PDF and transcript fields MUST be NULL

**Version anchor**: `canonical_version` MUST match current document version at creation

**Canonical text usage**: Used for both highlighting AND positional anchoring (byte offsets)

##### 3.1.2.2 PDF Anchors (`anchor_type='pdf'`)

Used for: PDF documents where highlights are rendered via pdf.js in browser/WebView.

**CRITICAL DISTINCTION**: PDF anchors use **pdf.js character offsets from text layer extraction**, NOT canonical text byte positions. Canonical text for PDFs is used **ONLY for retrieval indexing**, never for anchor positioning. This ensures highlights remain stable even when canonical text extraction code changes.

**`text_start`, `text_end`**:

- pdf.js character offsets in extracted text layer (NOT canonical_text byte offsets)
- Zero-indexed positions in pdf.js TextLayer
- `[start, end)` interval (inclusive start, exclusive end)
- These offsets are independent of `canonical_text` extraction

**`quote`**:

- The exact text extracted by pdf.js at `[text_start, text_end)` at creation time
- Maximum length: 10,000 bytes
- MUST be validated against pdf.js text layer, not canonical_text

**`prefix`, `suffix`**:

- Context extracted from pdf.js text layer (64 bytes each)
- Used for disambiguation during remap

**`pdf_page_number`** (REQUIRED):

- 1-indexed page number where highlight appears
- Used for efficient lookup during rendering

**`pdf_char_offset`** (REQUIRED):

- Character offset within the page (0-indexed)
- Enables binary search within page text layer

**`pdf_file_hash`** (REQUIRED):

- SHA256 of PDF file binary
- Used to detect when PDF changes; remap only triggered if hash differs
- Ensures highlights survive extraction code updates

**`pdf_extraction_confidence`** (OPTIONAL):

- Float in range [0.0, 1.0]
- Confidence score from pdf.js text extraction
- May be used to flag low-quality extractions

**Type-specific fields**: `pdf_page_number`, `pdf_char_offset`, `pdf_file_hash` MUST be non-NULL; transcript fields MUST be NULL

**Version anchor**: `canonical_version` MUST match current document version at creation (for retrieval consistency)

**Remapping behavior**: PDF highlights are remapped using pdf.js text layer extraction, NOT canonical_text. Remap algorithm searches within pdf.js extracted text for quote + prefix/suffix matches. Remap ONLY occurs if `pdf_file_hash` differs from current PDF file hash.

##### 3.1.2.3 Transcript Anchors (`anchor_type='transcript'`)

Used for: Episodes and videos where highlights reference transcript text and must support time-based navigation.

**`text_start`, `text_end`**:

- Zero-indexed byte positions in `transcript_text` (UTF-8 encoding)
- `[start, end)` interval (inclusive start, exclusive end)
- MUST satisfy: `0 ≤ text_start < text_end ≤ len(transcript_text)`

**`quote`**:

- The exact bytes `transcript_text[text_start:text_end]` at creation time
- Maximum length: 10,000 bytes
- MUST be validated at creation: `quote = transcript_text[text_start:text_end]`

**`prefix`, `suffix`**:

- Context extracted from `transcript_text` (64 bytes each)

**`time_start`, `time_end`** (REQUIRED):

- Floating-point timestamps in seconds (relative to media start)
- Derived from `transcript_segments` JSONB at creation time
- Used for:
  1. Seeking to highlight position in audio/video player
  2. Rendering time-coded links (e.g., "02:34 - 02:47")
  3. Fallback navigation if text remapping fails

**Type-specific fields**: `time_start`, `time_end` MUST be non-NULL; PDF fields MUST be NULL

**Version anchor**: `transcript_hash` MUST match current transcript hash at creation

**Remapping behavior**: Transcript highlights are remapped using `transcript_text`. If text remapping fails but `time_start`/`time_end` are still valid (within media duration), highlight MAY be kept as "time-only anchor" with `detached_reason = "text_detached_time_anchor_retained"`.

##### 3.1.2.4 Common Field Semantics

**Mutability**:

- **Immutable**: `media_type`, `media_id`, `anchor_type`, `text_start`, `text_end`, `quote`, `prefix`, `suffix`, `pdf_*`, `time_*`, version anchor (except via remap)
- **Mutable**: `color`, `is_hidden`, `is_public`, `is_detached`, `detached_reason`

**Quote length limit**: 10,000 bytes across all anchor types

#### 3.1.3 Invariants

**HL-1**: At creation, backend MUST verify anchor integrity based on `anchor_type`:

```python
def validate_highlight_creation(highlight):
    if highlight.anchor_type == 'text':
        canonical_text = get_canonical_text(highlight.media_type, highlight.media_id)
        assert canonical_text[highlight.text_start:highlight.text_end] == highlight.quote
        assert canonical_text[max(0, highlight.text_start - 64):highlight.text_start] == highlight.prefix
        assert canonical_text[highlight.text_end:min(len(canonical_text), highlight.text_end + 64)] == highlight.suffix
        assert highlight.canonical_version is not None
        assert highlight.pdf_page_number is None
        assert highlight.time_start is None

    elif highlight.anchor_type == 'pdf':
        # Validate against pdf.js text layer (NOT canonical_text)
        pdfjs_text = extract_pdfjs_text(highlight.media_id)
        assert pdfjs_text[highlight.text_start:highlight.text_end] == highlight.quote
        assert pdfjs_text[max(0, highlight.text_start - 64):highlight.text_start] == highlight.prefix
        assert pdfjs_text[highlight.text_end:min(len(pdfjs_text), highlight.text_end + 64)] == highlight.suffix
        assert highlight.canonical_version is not None
        assert highlight.pdf_page_number is not None
        assert highlight.pdf_char_offset is not None
        assert highlight.pdf_file_hash is not None
        assert highlight.time_start is None

    elif highlight.anchor_type == 'transcript':
        transcript_text = get_transcript_text(highlight.media_type, highlight.media_id)
        assert transcript_text[highlight.text_start:highlight.text_end] == highlight.quote
        assert transcript_text[max(0, highlight.text_start - 64):highlight.text_start] == highlight.prefix
        assert transcript_text[highlight.text_end:min(len(transcript_text), highlight.text_end + 64)] == highlight.suffix
        assert highlight.transcript_hash is not None
        assert highlight.time_start is not None
        assert highlight.time_end is not None
        assert highlight.time_end > highlight.time_start
        assert highlight.pdf_page_number is None

        # Validate time range is within media duration
        media = get_media(highlight.media_type, highlight.media_id)
        assert highlight.time_end <= media.duration_seconds
```

**HL-2**: Highlights MAY overlap. Rendering MUST stack overlapping highlights with shortest span on top (highest z-index).

**HL-3**: Highlights reference a specific version. When canonical text changes, highlights become **stale** and MUST be remapped.

**HL-4**: Detached highlights MUST preserve original `text_start`, `text_end`, `quote` for audit trail. They are not rendered inline but MUST be visible in a separate UI section.

### 3.2 Highlight Remapping

#### 3.2.1 Remap Trigger

A remap job MUST be enqueued when:

1. Document `canonical_version` increments
2. Episode/video `transcript_hash` changes
3. PDF file binary changes (detected via file hash mismatch)

**Input**:

```
remap_highlights(
  media_type: string,
  media_id: UUID,
  old_version: uint32 | string,
  new_version: uint32 | string,
  old_canonical_text: bytes,
  new_canonical_text: bytes
)
```

#### 3.2.2 Remap Algorithm

The remap algorithm dispatches based on `anchor_type`:

```python
def remap_highlight(H, old_version, new_version):
    if H.anchor_type == 'text':
        return remap_text_anchor(H, old_version, new_version)
    elif H.anchor_type == 'pdf':
        return remap_pdf_anchor(H, old_version, new_version)
    elif H.anchor_type == 'transcript':
        return remap_transcript_anchor(H, old_version, new_version)
    else:
        raise ValueError(f"Unknown anchor_type: {H.anchor_type}")

# ========== Text Anchor Remapping ==========

def remap_text_anchor(H, old_version, new_version):
    """Remap highlights anchored to canonical_text (EPUB, web articles)."""
    T_old = get_canonical_text(H.media_type, H.media_id, version=old_version)
    T_new = get_canonical_text(H.media_type, H.media_id, version=new_version)

    # Step 1: Exact match search
    matches = find_all_occurrences(H.quote, T_new)

    if len(matches) == 0:
        return fuzzy_search_text(H, T_new, new_version)

    if len(matches) == 1:
        return update_text_offsets(H, matches[0], T_new, new_version)

    # Step 2: Disambiguate using prefix/suffix
    scored_matches = []
    for match_start in matches:
        match_end = match_start + len(H.quote)
        prefix_new = T_new[max(0, match_start - 64):match_start]
        suffix_new = T_new[match_end:min(len(T_new), match_end + 64)]

        prefix_score = levenshtein_similarity(H.prefix, prefix_new)
        suffix_score = levenshtein_similarity(H.suffix, suffix_new)
        total_score = prefix_score + suffix_score

        scored_matches.append((match_start, total_score))

    # Take highest-scoring match
    best_match = max(scored_matches, key=lambda x: x[1])

    # Require minimum score threshold
    if best_match[1] < 0.8 * 2:  # 80% similarity on average
        return fuzzy_search_text(H, T_new, new_version)

    return update_text_offsets(H, best_match[0], T_new, new_version)

def fuzzy_search_text(H, T_new, new_version):
    # Compute edit distance for all substrings of length ±20% of quote length
    min_len = int(len(H.quote) * 0.8)
    max_len = int(len(H.quote) * 1.2)

    best_match = None
    best_distance = float('inf')

    for length in range(min_len, max_len + 1):
        for i in range(len(T_new) - length + 1):
            candidate = T_new[i:i + length]
            distance = levenshtein_distance(H.quote, candidate)

            if distance < best_distance:
                best_distance = distance
                best_match = i

    # Threshold: max 10% edit distance
    if best_distance <= len(H.quote) * 0.1:
        return update_text_offsets(H, best_match, T_new, new_version)

    # No match found
    return mark_detached(H, "text_not_found")

def update_text_offsets(H, new_start, T_new, new_version):
    new_end = new_start + len(H.quote)
    new_prefix = T_new[max(0, new_start - 64):new_start]
    new_suffix = T_new[new_end:min(len(T_new), new_end + 64)]

    UPDATE highlights
    SET
      text_start = new_start,
      text_end = new_end,
      prefix = new_prefix,
      suffix = new_suffix,
      canonical_version = new_version,
      is_detached = FALSE,
      detached_reason = NULL,
      updated_at = NOW()
    WHERE id = H.id

    return "remapped"

# ========== PDF Anchor Remapping ==========

def remap_pdf_anchor(H, old_version, new_version):
    """Remap highlights anchored to pdf.js text layer (PDFs only)."""
    # Check if PDF file has changed via file hash
    new_pdf_hash = get_pdf_file_hash(H.media_id)

    if new_pdf_hash == H.pdf_file_hash:
        # PDF binary unchanged; no remap needed
        return "pdf_unchanged"

    # Extract pdf.js text layer for new version
    pdfjs_text_new = extract_pdfjs_text(H.media_id, version=new_version)

    # Step 1: Exact match search
    matches = find_all_occurrences(H.quote, pdfjs_text_new)

    if len(matches) == 0:
        return fuzzy_search_pdf(H, pdfjs_text_new, new_pdf_hash)

    if len(matches) == 1:
        return update_pdf_offsets(H, matches[0], pdfjs_text_new, new_version, new_pdf_hash)

    # Step 2: Disambiguate using prefix/suffix
    scored_matches = []
    for match_start in matches:
        match_end = match_start + len(H.quote)
        prefix_new = pdfjs_text_new[max(0, match_start - 64):match_start]
        suffix_new = pdfjs_text_new[match_end:min(len(pdfjs_text_new), match_end + 64)]

        prefix_score = levenshtein_similarity(H.prefix, prefix_new)
        suffix_score = levenshtein_similarity(H.suffix, suffix_new)
        total_score = prefix_score + suffix_score

        scored_matches.append((match_start, total_score))

    best_match = max(scored_matches, key=lambda x: x[1])

    if best_match[1] < 0.8 * 2:
        return fuzzy_search_pdf(H, pdfjs_text_new, new_pdf_hash)

    return update_pdf_offsets(H, best_match[0], pdfjs_text_new, new_version, new_pdf_hash)

def fuzzy_search_pdf(H, pdfjs_text_new, new_pdf_hash):
    min_len = int(len(H.quote) * 0.8)
    max_len = int(len(H.quote) * 1.2)

    best_match = None
    best_distance = float('inf')

    for length in range(min_len, max_len + 1):
        for i in range(len(pdfjs_text_new) - length + 1):
            candidate = pdfjs_text_new[i:i + length]
            distance = levenshtein_distance(H.quote, candidate)

            if distance < best_distance:
                best_distance = distance
                best_match = i

    if best_distance <= len(H.quote) * 0.1:
        return update_pdf_offsets(H, best_match, pdfjs_text_new, None, new_pdf_hash)

    return mark_detached(H, "pdf_text_not_found")

def update_pdf_offsets(H, new_start, pdfjs_text_new, new_version, new_pdf_hash):
    new_end = new_start + len(H.quote)
    new_prefix = pdfjs_text_new[max(0, new_start - 64):new_start]
    new_suffix = pdfjs_text_new[new_end:min(len(pdfjs_text_new), new_end + 64)]

    # Recompute page number and char offset from pdf.js text layer
    new_page_number, new_char_offset = compute_pdf_page_position(H.media_id, new_start, new_version)

    UPDATE highlights
    SET
      text_start = new_start,
      text_end = new_end,
      prefix = new_prefix,
      suffix = new_suffix,
      pdf_page_number = new_page_number,
      pdf_char_offset = new_char_offset,
      pdf_file_hash = new_pdf_hash,
      canonical_version = new_version,
      is_detached = FALSE,
      detached_reason = NULL,
      updated_at = NOW()
    WHERE id = H.id

    return "remapped"

# ========== Transcript Anchor Remapping ==========

def remap_transcript_anchor(H, old_hash, new_hash):
    """Remap highlights anchored to transcript_text (episodes, videos)."""
    T_old = get_transcript_text(H.media_type, H.media_id, hash=old_hash)
    T_new = get_transcript_text(H.media_type, H.media_id, hash=new_hash)

    # Step 1: Exact match search
    matches = find_all_occurrences(H.quote, T_new)

    if len(matches) == 0:
        return fuzzy_search_transcript(H, T_new, new_hash)

    if len(matches) == 1:
        return update_transcript_offsets(H, matches[0], T_new, new_hash)

    # Step 2: Disambiguate using prefix/suffix
    scored_matches = []
    for match_start in matches:
        match_end = match_start + len(H.quote)
        prefix_new = T_new[max(0, match_start - 64):match_start]
        suffix_new = T_new[match_end:min(len(T_new), match_end + 64)]

        prefix_score = levenshtein_similarity(H.prefix, prefix_new)
        suffix_score = levenshtein_similarity(H.suffix, suffix_new)
        total_score = prefix_score + suffix_score

        scored_matches.append((match_start, total_score))

    best_match = max(scored_matches, key=lambda x: x[1])

    if best_match[1] < 0.8 * 2:
        return fuzzy_search_transcript(H, T_new, new_hash)

    return update_transcript_offsets(H, best_match[0], T_new, new_hash)

def fuzzy_search_transcript(H, T_new, new_hash):
    min_len = int(len(H.quote) * 0.8)
    max_len = int(len(H.quote) * 1.2)

    best_match = None
    best_distance = float('inf')

    for length in range(min_len, max_len + 1):
        for i in range(len(T_new) - length + 1):
            candidate = T_new[i:i + length]
            distance = levenshtein_distance(H.quote, candidate)

            if distance < best_distance:
                best_distance = distance
                best_match = i

    if best_distance <= len(H.quote) * 0.1:
        return update_transcript_offsets(H, best_match, T_new, new_hash)

    # Transcript-specific fallback: check if time range is still valid
    media = get_media(H.media_type, H.media_id)
    if H.time_end <= media.duration_seconds:
        # Keep as time-only anchor (text detached but time valid)
        return mark_time_only_anchor(H, new_hash)

    # Both text and time invalid
    return mark_detached(H, "transcript_text_and_time_invalid")

def update_transcript_offsets(H, new_start, T_new, new_hash):
    new_end = new_start + len(H.quote)
    new_prefix = T_new[max(0, new_start - 64):new_start]
    new_suffix = T_new[new_end:min(len(T_new), new_end + 64)]

    # Recompute time range from transcript_segments
    new_time_start, new_time_end = compute_time_range_from_offsets(
        H.media_type, H.media_id, new_start, new_end
    )

    UPDATE highlights
    SET
      text_start = new_start,
      text_end = new_end,
      prefix = new_prefix,
      suffix = new_suffix,
      time_start = new_time_start,
      time_end = new_time_end,
      transcript_hash = new_hash,
      is_detached = FALSE,
      detached_reason = NULL,
      updated_at = NOW()
    WHERE id = H.id

    return "remapped"

def mark_time_only_anchor(H, new_hash):
    """Keep highlight as time-only anchor when text remapping fails but time is valid."""
    UPDATE highlights
    SET
      transcript_hash = new_hash,
      is_detached = FALSE,
      detached_reason = "text_detached_time_anchor_retained",
      updated_at = NOW()
    WHERE id = H.id

    return "time_only_anchor"

# ========== Common Helpers ==========

def mark_detached(H, reason):
    UPDATE highlights
    SET
      is_detached = TRUE,
      detached_reason = reason,
      updated_at = NOW()
    WHERE id = H.id

    return "detached"
```

#### 3.2.3 Remap Job Specification

**Job name**: `remap_highlights`

**Inputs**:

- `media_type: string`
- `media_id: UUID`
- `old_version: string` (canonical_version as string or transcript_hash)
- `new_version: string`

**Preconditions**:

- Media exists with new version
- Highlights exist with old version

**Idempotency key**:

```
(media_type, media_id, new_version)
```

If all highlights already reference `new_version`, skip job.

**Success postconditions**:

- All highlights either remapped to new version or marked detached
- Metrics logged: `highlights_remapped_count`, `highlights_detached_count`

**Failure postconditions**:

- Partial remaps MAY have occurred (remap is row-level atomic)
- Job retries up to 3 times
- After max retries, remaining highlights marked detached with `detached_reason = "remap_job_failed"`

**Retry policy**:

- Max attempts: 3
- Backoff: 1m, 5m, 15m

#### 3.2.4 Concurrency

Remap jobs MUST acquire row-level locks to prevent concurrent updates:

```sql
SELECT * FROM highlights
WHERE media_type = :media_type AND media_id = :media_id
  AND (canonical_version = :old_version OR transcript_hash = :old_version)
FOR UPDATE
```

---

## 4. Visibility Model and Threat Model

### 4.1 Visibility Function

All access control is governed by a single pure function:

```
Visible(U: UUID, O: Object) → bool
```

Where:

- `U` is a user ID
- `O` is any entity (document, episode, video, highlight, annotation, conversation, message)

### 4.2 Visibility Rules

#### 4.2.1 Media Visibility

**Documents**:

```sql
Visible(U, document D) :=
  EXISTS (
    SELECT 1 FROM library_memberships lm
    JOIN library_media lmed ON lm.library_id = lmed.library_id
    WHERE lm.user_id = U
      AND lmed.media_type = 'document'
      AND lmed.media_id = D.id
  )
```

**Episodes**:

```sql
Visible(U, episode E) :=
  EXISTS (
    SELECT 1 FROM subscriptions s
    WHERE s.user_id = U
      AND s.podcast_id = E.podcast_id
  )
```

**Videos**:

```sql
Visible(U, video V) :=
  EXISTS (
    SELECT 1 FROM library_memberships lm
    JOIN library_media lmed ON lm.library_id = lmed.library_id
    WHERE lm.user_id = U
      AND lmed.media_type = 'video'
      AND lmed.media_id = V.id
  )
```

#### 4.2.2 User-Owned Object Visibility

**Highlights**:

```sql
Visible(U, highlight H) :=
  Visible(U, media_of(H))  -- media MUST be visible
  AND
  (
    (H.user_id = U)  -- owner
    OR
    (H.is_public = TRUE)  -- public
    OR
    EXISTS (  -- shared into accessible library
      SELECT 1 FROM object_library_visibility olv
      JOIN library_memberships lm ON olv.library_id = lm.library_id
      WHERE olv.object_type = 'highlight'
        AND olv.object_id = H.id
        AND lm.user_id = U
    )
  )
```

**Annotations**:

```sql
Visible(U, annotation A) := Visible(U, highlight_of(A))
```

**Conversations**:

```sql
Visible(U, conversation C) :=
  (C.user_id = U)
  OR
  (C.is_public = TRUE)
  OR
  EXISTS (
    SELECT 1 FROM object_library_visibility olv
    JOIN library_memberships lm ON olv.library_id = lm.library_id
    WHERE olv.object_type = 'conversation'
      AND olv.object_id = C.id
      AND lm.user_id = U
  )
```

**Messages**:

```sql
Visible(U, message M) :=
  (M.user_id = U)
  OR
  (M.is_public = TRUE AND Visible(U, conversation_of(M)))
  OR
  EXISTS (
    SELECT 1 FROM object_library_visibility olv
    JOIN library_memberships lm ON olv.library_id = lm.library_id
    WHERE olv.object_type = 'message'
      AND olv.object_id = M.id
      AND lm.user_id = U
      AND Visible(U, conversation_of(M))
  )
```

**Private message stubs**:

If `Visible(U, conversation C)` is true but `Visible(U, message M in C)` is false, the API MUST return:

```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "role": "user",
  "content": "[Private message]",
  "created_at": "2024-11-21T10:00:00Z",
  "is_stub": true
}
```

Metadata leaked: `id`, `conversation_id`, `role`, `created_at`, `is_stub`. Content, model, and other fields MUST be omitted.

### 4.3 Enforcement Points

#### 4.3.1 API Layer

**All list endpoints** MUST filter results via `Visible(U, O)`:

```typescript
async function listDocuments(userId: UUID): Promise<Document[]> {
  const candidates = await db.query(`
    SELECT d.* FROM documents d
    WHERE d.deleted_at IS NULL
      AND EXISTS (
        SELECT 1 FROM library_memberships lm
        JOIN library_media lmed ON lm.library_id = lmed.library_id
        WHERE lm.user_id = $1
          AND lmed.media_type = 'document'
          AND lmed.media_id = d.id
      )
  `, [userId]);

  return candidates;
}
```

**Single-object endpoints** MUST return 404 (not 403) if `Visible(U, O)` is false:

```typescript
async function getDocument(userId: UUID, docId: UUID): Promise<Document> {
  const doc = await db.findOne('documents', { id: docId });

  if (!doc || !await isVisible(userId, doc)) {
    throw new NotFoundError();  // 404, not 403
  }

  return doc;
}
```

Rationale: Returning 403 leaks object existence.

#### 4.3.2 Retrieval Layer

Vector search MUST post-filter all candidates:

```typescript
async function vectorSearch(
  userId: UUID,
  query: string,
  k: number
): Promise<Chunk[]> {
  const embedding = await embed(query);

  // Overfetch
  const candidates = await vectorStore.search(embedding, k * 5);

  // Map to source objects
  const sourceIds = candidates.map(c => ({ type: c.source_type, id: c.source_id }));

  // Bulk visibility check
  const visibleIds = await filterVisible(userId, sourceIds);
  const visibleIdSet = new Set(visibleIds.map(x => `${x.type}:${x.id}`));

  // Filter chunks
  const filtered = candidates.filter(c =>
    visibleIdSet.has(`${c.source_type}:${c.source_id}`)
  );

  // Re-rank and limit
  filtered.sort((a, b) => b.similarity - a.similarity);
  return filtered.slice(0, k);
}
```

#### 4.3.3 LLM Context Layer

All chunks included in LLM context MUST pass `Visible(U, O)` check:

```typescript
async function assembleLLMContext(
  userId: UUID,
  conversationId: UUID,
  query: string
): Promise<LLMContext> {
  const retrievedChunks = await vectorSearch(userId, query, 20);

  // Additional visibility verification (defense in depth)
  const verifiedChunks = [];
  for (const chunk of retrievedChunks) {
    const source = await loadSourceObject(chunk.source_type, chunk.source_id);
    if (await isVisible(userId, source)) {
      verifiedChunks.push(chunk);
    }
  }

  return {
    systemMessage: buildSystemMessage(conversationId),
    history: await loadHistory(conversationId, userId),
    retrieval: verifiedChunks
  };
}
```

### 4.4 Threat Model

#### 4.4.1 Adversary Capabilities

**Assumed adversary**:

- Authenticated user with valid account
- Can make arbitrary API requests within rate limits
- Can inspect all client-side code (web/mobile)
- Cannot access database directly
- Cannot intercept other users' TLS traffic

**Attack vectors**:

1. Direct object access (guessing UUIDs, enumerating IDs)
2. Retrieval overfetch inspection (inferring existence via vector search timing)
3. Link graph traversal (following references to invisible objects)
4. Metadata leaks (timestamps, counts, error messages revealing invisible data)

#### 4.4.2 Security Guarantees

**G-1**: An adversary MUST NOT learn the existence of objects for which `Visible(U, O) = false`

**G-2**: API responses MUST NOT leak:

- Object IDs of invisible objects
- Content snippets of invisible objects
- Embeddings of invisible objects
- Counts of invisible objects (e.g., "5 more private messages")
- Timestamps of invisible objects (except for message stubs as specified)

**G-3**: Retrieval timing MUST NOT leak invisible object existence:

- Vector search executes identically regardless of result visibility
- Post-filtering happens in application layer, not database (constant-time from adversary perspective)

**G-4**: Error messages MUST NOT distinguish between "object does not exist" and "object exists but you cannot access it"

- Use 404 for both cases

#### 4.4.3 Metadata Leak Tolerance

The following metadata leaks are **acceptable**:

- Private message stubs reveal: existence, timestamp, author ID, role (see §4.2.2)
- Deleted objects may reveal: creation timestamp in audit logs (30-day retention)

The following are **forbidden**:

- Chunk embeddings of invisible content in vector store responses
- Mention of invisible object IDs in link traversal
- Retrieval result counts that change based on invisible content

---

## 5. Retrieval Contracts

### 5.1 Embedding Spaces

Three disjoint embedding spaces:

#### 5.1.1 Space A: Content Chunks

**Sources**:

- Document `canonical_text`
- Episode `transcript_text`
- Video `transcript_text`

**Schema**:

```sql
CREATE TABLE content_chunks (
  id UUID PRIMARY KEY,
  media_type TEXT NOT NULL CHECK (media_type IN ('document', 'episode', 'video')),
  media_id UUID NOT NULL,

  chunk_version TEXT NOT NULL,
  embedding_model TEXT NOT NULL,

  text_start BIGINT NOT NULL,
  text_end BIGINT NOT NULL,
  text TEXT NOT NULL,

  embedding vector(1536) NOT NULL,

  metadata JSONB NOT NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_content_chunks_media ON content_chunks(media_type, media_id);
CREATE INDEX idx_content_chunks_vector ON content_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Metadata fields**:

- `section_title: string | null` (for documents)
- `time_start: float64`, `time_end: float64` (for transcripts)

#### 5.1.2 Space B: Thought Chunks

**Sources**:

- Annotations
- Messages
- Conversation summaries

**Schema**:

```sql
CREATE TABLE thought_chunks (
  id UUID PRIMARY KEY,
  object_type TEXT NOT NULL CHECK (object_type IN ('annotation', 'message', 'conversation_summary')),
  object_id UUID NOT NULL,
  user_id UUID NOT NULL,

  chunk_version TEXT NOT NULL,
  embedding_model TEXT NOT NULL,

  text TEXT NOT NULL,
  embedding vector(1536) NOT NULL,

  metadata JSONB NOT NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_thought_chunks_user ON thought_chunks(user_id);
CREATE INDEX idx_thought_chunks_object ON thought_chunks(object_type, object_id);
CREATE INDEX idx_thought_chunks_vector ON thought_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Metadata fields**:

- `conversation_id: UUID | null` (for messages)
- `media_type: string`, `media_id: UUID` (for annotations)

#### 5.1.3 Space C: Metadata Chunks

**Sources**:

- Document titles, authors, descriptions
- Podcast/episode titles, descriptions
- Video titles, channel names

**Schema**:

```sql
CREATE TABLE metadata_chunks (
  id UUID PRIMARY KEY,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('document', 'episode', 'video', 'podcast')),
  entity_id UUID NOT NULL,

  chunk_version TEXT NOT NULL,
  embedding_model TEXT NOT NULL,

  text TEXT NOT NULL,
  embedding vector(1536) NOT NULL,

  metadata JSONB NOT NULL,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_metadata_chunks_entity ON metadata_chunks(entity_type, entity_id);
CREATE INDEX idx_metadata_chunks_vector ON metadata_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 5.2 Chunking Strategy

#### 5.2.1 Document Chunking

**Algorithm**:

```python
def chunk_document(doc: Document) -> List[ContentChunk]:
    chunks = []
    sections = parse_sections(doc.structure)

    for section in sections:
        section_text = doc.canonical_text[section.text_start:section.text_end]

        if len(section_text) <= MAX_CHUNK_CHARS:
            # Small section: single chunk
            chunks.append(create_chunk(
                text=section_text,
                text_start=section.text_start,
                text_end=section.text_end,
                metadata={'section_title': section.title}
            ))
        else:
            # Large section: sliding window
            chunks.extend(sliding_window_chunks(
                text=section_text,
                start_offset=section.text_start,
                window_size=CHUNK_SIZE,
                overlap=CHUNK_OVERLAP,
                section_title=section.title
            ))

    return chunks

MAX_CHUNK_CHARS = 1600  # ~400 tokens
CHUNK_SIZE = 1600
CHUNK_OVERLAP = 400  # ~100 tokens
```

**Embedding text format**:

```
Title: {document.title}
Author: {document.author}
Section: {section_title}

{chunk_text}
```

#### 5.2.2 Transcript Chunking

**Algorithm**:

```python
def chunk_transcript(media: Episode | Video) -> List[ContentChunk]:
    chunks = []
    segments = media.transcript_segments

    current_chunk_segments = []
    current_duration = 0

    for segment in segments:
        segment_duration = segment.time_end - segment.time_start

        if current_duration + segment_duration > TIME_WINDOW:
            # Emit chunk
            chunks.append(merge_segments(current_chunk_segments, media))

            # Start new chunk with overlap
            overlap_segments = current_chunk_segments[-OVERLAP_SEGMENTS:]
            current_chunk_segments = overlap_segments + [segment]
            current_duration = sum(s.time_end - s.time_start for s in current_chunk_segments)
        else:
            current_chunk_segments.append(segment)
            current_duration += segment_duration

    # Emit final chunk
    if current_chunk_segments:
        chunks.append(merge_segments(current_chunk_segments, media))

    return chunks

TIME_WINDOW = 30.0  # seconds
OVERLAP_SEGMENTS = 2  # ~5 seconds overlap
```

**Embedding text format**:

```
{podcast_title} - {episode_title}
Timestamp: {time_start}s - {time_end}s

{chunk_text}
```

#### 5.2.3 Thought Chunking

**Annotations**:

```
Annotation on "{highlight.quote}" from {media.title}

{annotation.content}
```

**Messages**:

If message ≤ 1000 tokens: single chunk.
If message > 1000 tokens: split with 100-token overlap.

```
Message in conversation "{conversation.title}"

{message.content[chunk_range]}
```

**Conversation summaries**:

```
Conversation "{conversation.title}" summary

{conversation.summary_state}
```

### 5.3 Retrieval API

#### 5.3.1 Request Schema

```typescript
interface RetrievalRequest {
  query: string;
  scope: RetrievalScope;
  spaces: ('content' | 'thoughts' | 'metadata')[];
  k: number;  // desired result count
  user_id: UUID;  // from auth context
}

type RetrievalScope =
  | { type: 'document', document_id: UUID }
  | { type: 'episode', episode_id: UUID }
  | { type: 'video', video_id: UUID }
  | { type: 'library', library_id: UUID }
  | { type: 'my_notes' }
  | { type: 'global' };
```

#### 5.3.2 Response Schema

```typescript
interface RetrievalResponse {
  results: RetrievalResult[];
  total_candidates: number;  // before visibility filter
  filtered_count: number;    // after visibility filter
  query_embedding_ms: number;
  search_ms: number;
  filter_ms: number;
}

interface RetrievalResult {
  chunk_id: UUID;
  chunk_type: 'content' | 'thought' | 'metadata';

  source_type: string;  // 'document', 'episode', 'video', 'annotation', 'message', etc.
  source_id: UUID;

  text: string;
  text_start?: number;  // for content chunks
  text_end?: number;

  similarity: number;  // 0-1

  metadata: {
    title?: string;
    section_title?: string;
    time_start?: number;
    time_end?: number;
    conversation_id?: UUID;
  };
}
```

#### 5.3.3 Retrieval Algorithm

```typescript
async function retrieve(req: RetrievalRequest): Promise<RetrievalResponse> {
  const startTime = Date.now();

  // 1. Embed query
  const queryEmbedding = await embedText(req.query);
  const embeddingTime = Date.now() - startTime;

  // 2. Overfetch from vector store
  const K_PRIME = req.k * 5;  // overfetch factor
  const candidates: Chunk[] = [];

  if (req.spaces.includes('content')) {
    candidates.push(...await vectorStore.search('content_chunks', queryEmbedding, K_PRIME));
  }
  if (req.spaces.includes('thoughts')) {
    candidates.push(...await vectorStore.search('thought_chunks', queryEmbedding, K_PRIME));
  }
  if (req.spaces.includes('metadata')) {
    candidates.push(...await vectorStore.search('metadata_chunks', queryEmbedding, K_PRIME));
  }

  const searchTime = Date.now() - startTime - embeddingTime;

  // 3. Apply scope filter
  const scopeFiltered = applyScopeFilter(candidates, req.scope);

  // 4. Apply visibility filter
  const visibilityStart = Date.now();
  const visibleChunks = await filterVisibleChunks(req.user_id, scopeFiltered);
  const filterTime = Date.now() - visibilityStart;

  // 5. Deduplicate and group
  const deduplicated = deduplicateChunks(visibleChunks);

  // 6. Re-rank
  const reranked = rerank(deduplicated, req);

  // 7. Limit to k
  const final = reranked.slice(0, req.k);

  return {
    results: final,
    total_candidates: candidates.length,
    filtered_count: visibleChunks.length,
    query_embedding_ms: embeddingTime,
    search_ms: searchTime,
    filter_ms: filterTime
  };
}
```

#### 5.3.4 Scope Filter Implementation

```typescript
function applyScopeFilter(chunks: Chunk[], scope: RetrievalScope): Chunk[] {
  switch (scope.type) {
    case 'document':
      return chunks.filter(c =>
        c.source_type === 'document' && c.source_id === scope.document_id
      );

    case 'episode':
      return chunks.filter(c =>
        c.source_type === 'episode' && c.source_id === scope.episode_id
      );

    case 'video':
      return chunks.filter(c =>
        c.source_type === 'video' && c.source_id === scope.video_id
      );

    case 'library':
      const libraryMediaIds = await getLibraryMediaIds(scope.library_id);
      return chunks.filter(c => {
        const key = `${c.source_type}:${c.source_id}`;
        return libraryMediaIds.has(key);
      });

    case 'my_notes':
      return chunks.filter(c => c.chunk_type === 'thought');

    case 'global':
      return chunks;
  }
}
```

#### 5.3.5 Deduplication

```typescript
function deduplicateChunks(chunks: Chunk[]): Chunk[] {
  const grouped = groupBy(chunks, c => `${c.source_type}:${c.source_id}`);

  const deduplicated: Chunk[] = [];

  for (const [key, group] of grouped) {
    // Sort by similarity descending
    group.sort((a, b) => b.similarity - a.similarity);

    // Take top 3 chunks per source
    const top = group.slice(0, 3);

    // Merge contiguous chunks
    const merged = mergeContiguousChunks(top);

    deduplicated.push(...merged);
  }

  return deduplicated;
}

function mergeContiguousChunks(chunks: ContentChunk[]): Chunk[] {
  // Only applicable to content chunks with text_start/text_end
  if (chunks.length === 0 || !('text_start' in chunks[0])) {
    return chunks;
  }

  chunks.sort((a, b) => a.text_start - b.text_start);

  const merged: Chunk[] = [];
  let current = chunks[0];

  for (let i = 1; i < chunks.length; i++) {
    if (chunks[i].text_start === current.text_end) {
      // Contiguous: merge
      current = {
        ...current,
        text_end: chunks[i].text_end,
        text: current.text + chunks[i].text,
        similarity: Math.max(current.similarity, chunks[i].similarity)
      };
    } else {
      merged.push(current);
      current = chunks[i];
    }
  }

  merged.push(current);
  return merged;
}
```

#### 5.3.6 Reranking

```typescript
function rerank(chunks: Chunk[], req: RetrievalRequest): Chunk[] {
  // Apply type weights
  const weighted = chunks.map(c => ({
    ...c,
    weighted_similarity: c.similarity * getTypeWeight(c.chunk_type)
  }));

  // Sort by weighted similarity descending
  weighted.sort((a, b) => b.weighted_similarity - a.weighted_similarity);

  return weighted;
}

function getTypeWeight(type: 'content' | 'thought' | 'metadata'): number {
  switch (type) {
    case 'content': return 1.0;
    case 'thought': return 1.1;  // boost user's own thoughts
    case 'metadata': return 0.9;
  }
}
```

#### 5.3.7 Failure Semantics

**Vector store unreachable**:

- Return 503 Service Unavailable
- Error message: `"Retrieval service temporarily unavailable"`
- Retry-After header: 60 seconds

**Embedding provider timeout**:

- Timeout: 10 seconds
- Return 504 Gateway Timeout
- Error message: `"Query embedding timeout"`

**Partial results**:

If some vector stores succeed and others fail (e.g., content_chunks succeeds but thought_chunks fails):

- Return partial results with warning
- Response includes `warnings: string[]` field

```json
{
  "results": [...],
  "warnings": ["Thought search unavailable, showing content results only"]
}
```

---

## 6. Context Packaging Specification

### 6.1 Context Assembly Algorithm

```typescript
interface LLMContext {
  systemMessage: string;
  history: Message[];
  retrievalContent: RetrievalResult[];
  retrievalThoughts: RetrievalResult[];
  retrievalMetadata: RetrievalResult[];
  totalTokens: number;
}

async function assembleContext(
  conversationId: UUID,
  userId: UUID,
  userMessage: string
): Promise<LLMContext> {
  // 1. Load conversation
  const conversation = await loadConversation(conversationId);

  // 2. Build system message
  const systemMessage = buildSystemMessage(conversation);
  const systemTokens = countTokens(systemMessage);

  // 3. Load history
  const historyMessages = await loadHistory(conversationId, userId);
  const historyTokens = countTokens(historyMessages);

  // 4. Perform retrieval
  const contentResults = await retrieve({
    query: userMessage,
    scope: { type: 'global' },
    spaces: ['content'],
    k: 8,
    user_id: userId
  });

  const thoughtResults = await retrieve({
    query: userMessage,
    scope: { type: 'global' },
    spaces: ['thoughts'],
    k: 5,
    user_id: userId
  });

  const metadataResults = await retrieve({
    query: userMessage,
    scope: { type: 'global' },
    spaces: ['metadata'],
    k: 3,
    user_id: userId
  });

  const retrievalTokens =
    countTokens(contentResults) +
    countTokens(thoughtResults) +
    countTokens(metadataResults);

  const userMessageTokens = countTokens(userMessage);

  // 5. Check budget
  const totalTokens =
    systemTokens +
    historyTokens +
    retrievalTokens +
    userMessageTokens;

  const BUDGET = 32000;
  const RESERVE = 7500;  // for completion

  if (totalTokens > BUDGET - RESERVE) {
    // Apply shrinking strategy
    return shrinkContext({
      systemMessage,
      systemTokens,
      history: historyMessages,
      historyTokens,
      contentResults,
      thoughtResults,
      metadataResults,
      retrievalTokens,
      userMessage,
      userMessageTokens,
      budget: BUDGET - RESERVE
    });
  }

  return {
    systemMessage,
    history: historyMessages,
    retrievalContent: contentResults.results,
    retrievalThoughts: thoughtResults.results,
    retrievalMetadata: metadataResults.results,
    totalTokens
  };
}
```

### 6.2 System Message Construction

```typescript
function buildSystemMessage(conversation: Conversation): string {
  let message = `You are a helpful assistant with access to the user's personal knowledge base of documents, podcasts, videos, annotations, and conversations.

When answering questions, cite specific sources by title and location (page number, timestamp, or section).

`;

  if (conversation.summary_state) {
    message += `## Conversation Summary

${conversation.summary_state}

`;
  }

  message += `Provide thoughtful, accurate answers based on the available context.`;

  return message;
}
```

### 6.3 History Selection

```typescript
async function loadHistory(
  conversationId: UUID,
  userId: UUID
): Promise<Message[]> {
  // Load last 20 messages in conversation
  const rawMessages = await db.query(`
    SELECT * FROM messages
    WHERE conversation_id = $1
    ORDER BY created_at DESC
    LIMIT 20
  `, [conversationId]);

  // Reverse to chronological order
  rawMessages.reverse();

  // Filter by visibility
  const visibleMessages = [];
  for (const msg of rawMessages) {
    if (await isVisible(userId, msg)) {
      visibleMessages.push(msg);
    } else {
      // Include stub for private messages
      visibleMessages.push({
        id: msg.id,
        role: msg.role,
        content: '[Private message]',
        created_at: msg.created_at,
        is_stub: true
      });
    }
  }

  return visibleMessages;
}
```

### 6.4 Token Budget Shrinking

```typescript
interface ContextShrinkInput {
  systemMessage: string;
  systemTokens: number;
  history: Message[];
  historyTokens: number;
  contentResults: RetrievalResponse;
  thoughtResults: RetrievalResponse;
  metadataResults: RetrievalResponse;
  retrievalTokens: number;
  userMessage: string;
  userMessageTokens: number;
  budget: number;
}

function shrinkContext(input: ContextShrinkInput): LLMContext {
  const {
    systemMessage,
    systemTokens,
    history,
    contentResults,
    thoughtResults,
    metadataResults,
    userMessage,
    userMessageTokens,
    budget
  } = input;

  // Priority: system > user message > history > content > thoughts > metadata

  let availableForContext = budget - systemTokens - userMessageTokens;

  if (availableForContext <= 0) {
    throw new Error('User message too long');
  }

  // Level 1: Shrink to standard allocation
  let historyBudget = Math.min(8000, availableForContext * 0.4);
  let contentBudget = Math.min(8000, availableForContext * 0.4);
  let thoughtBudget = Math.min(4000, availableForContext * 0.15);
  let metadataBudget = Math.min(500, availableForContext * 0.05);

  // Level 2: If still over budget, shrink proportionally
  const totalAllocated = historyBudget + contentBudget + thoughtBudget + metadataBudget;
  if (totalAllocated > availableForContext) {
    const scale = availableForContext / totalAllocated;
    historyBudget *= scale;
    contentBudget *= scale;
    thoughtBudget *= scale;
    metadataBudget *= scale;
  }

  // Truncate each section
  const truncatedHistory = truncateMessages(history, historyBudget);
  const truncatedContent = truncateResults(contentResults.results, contentBudget);
  const truncatedThoughts = truncateResults(thoughtResults.results, thoughtBudget);
  const truncatedMetadata = truncateResults(metadataResults.results, metadataBudget);

  const finalTokens =
    systemTokens +
    userMessageTokens +
    countTokens(truncatedHistory) +
    countTokens(truncatedContent) +
    countTokens(truncatedThoughts) +
    countTokens(truncatedMetadata);

  return {
    systemMessage,
    history: truncatedHistory,
    retrievalContent: truncatedContent,
    retrievalThoughts: truncatedThoughts,
    retrievalMetadata: truncatedMetadata,
    totalTokens: finalTokens
  };
}

function truncateMessages(messages: Message[], budget: number): Message[] {
  // Keep most recent messages within budget
  const result: Message[] = [];
  let tokens = 0;

  for (let i = messages.length - 1; i >= 0; i--) {
    const msgTokens = countTokens(messages[i].content);
    if (tokens + msgTokens > budget) {
      break;
    }
    result.unshift(messages[i]);
    tokens += msgTokens;
  }

  return result;
}

function truncateResults(results: RetrievalResult[], budget: number): RetrievalResult[] {
  const truncated: RetrievalResult[] = [];
  let tokens = 0;

  for (const result of results) {
    const resultTokens = countTokens(result.text);
    if (tokens + resultTokens > budget) {
      break;
    }
    truncated.push(result);
    tokens += resultTokens;
  }

  return truncated;
}
```

### 6.5 Prompt Structure

```typescript
function buildPrompt(context: LLMContext, userMessage: string): ProviderPrompt {
  // System section
  let prompt = context.systemMessage + '\n\n';

  // History section
  if (context.history.length > 0) {
    prompt += '## Conversation History\n\n';
    for (const msg of context.history) {
      prompt += `**${msg.role}**: ${msg.content}\n\n`;
    }
  }

  // Retrieval sections
  if (context.retrievalContent.length > 0) {
    prompt += '## Retrieved Content\n\n';
    for (const result of context.retrievalContent) {
      prompt += formatRetrievalResult(result) + '\n\n';
    }
  }

  if (context.retrievalThoughts.length > 0) {
    prompt += '## Your Notes and Thoughts\n\n';
    for (const result of context.retrievalThoughts) {
      prompt += formatRetrievalResult(result) + '\n\n';
    }
  }

  if (context.retrievalMetadata.length > 0) {
    prompt += '## Available Documents\n\n';
    for (const result of context.retrievalMetadata) {
      prompt += `- ${result.text}\n`;
    }
    prompt += '\n';
  }

  // Current user message
  prompt += `## Current Question\n\n**user**: ${userMessage}\n\n`;
  prompt += `**assistant**: `;

  return { text: prompt };
}

function formatRetrievalResult(result: RetrievalResult): string {
  let header = '';

  if (result.chunk_type === 'content') {
    header = `[${result.metadata.title}`;
    if (result.metadata.section_title) {
      header += `, ${result.metadata.section_title}`;
    }
    if (result.metadata.time_start !== undefined) {
      const timeStr = formatTimestamp(result.metadata.time_start);
      header += `, ${timeStr}`;
    }
    header += ']';
  } else if (result.chunk_type === 'thought') {
    if (result.source_type === 'annotation') {
      header = `[Your note on "${result.metadata.title}"]`;
    } else if (result.source_type === 'message') {
      header = `[Your message in "${result.metadata.title}"]`;
    }
  }

  return `${header}\n${result.text}`;
}

function formatTimestamp(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
```

### 6.6 Per-Message Model Choice

Each message stores `effective_model_id`:

```sql
ALTER TABLE messages ADD COLUMN effective_model_id TEXT NOT NULL DEFAULT 'gpt-4-turbo';
```

**Supported models** (as of 2024-11-25):

- `gpt-4-turbo` (OpenAI)
- `gpt-4o` (OpenAI)
- `claude-3-5-sonnet-20241022` (Anthropic)
- `claude-3-opus-20240229` (Anthropic)
- `gemini-1.5-pro` (Google)

**Model selection**:

- User chooses model via UI dropdown when sending message
- Default: `gpt-4-turbo`

**Context assembly**:

- Identical across all models (same retrieval, same history)
- Provider-specific formatting applied at call time (e.g., Anthropic XML tags vs OpenAI JSON messages)

**No replay guarantee**:

The system DOES NOT guarantee bitwise-identical outputs when:

- Same input message re-generated
- Model version updated by provider (e.g., OpenAI deploys new `gpt-4-turbo` checkpoint)
- Temperature > 0 (stochastic sampling)

This is acceptable and expected behavior.

---

## 7. Job Orchestration and State Machines

### 7.1 Phase 1 Job Specifications

#### 7.1.1 Job: `ingest_document`

**Inputs**:

```typescript
{
  document_id: UUID,
  blob_key: string,
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

#### 7.1.2 Job: `canonicalize_document`

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

1. Download blob
2. Detect format (PDF/EPUB/HTML)
3. Extract canonical text per §2.2.2
4. Compute `canonical_hash = SHA256(canonical_text)`
5. Determine if version increment needed:
   - If existing `canonical_hash` differs: increment `canonical_version`
6. Extract structure (blocks, sections)
7. Extract metadata (title, author, etc.)
8. Write atomically:

```sql
UPDATE documents SET
  canonical_text = $1,
  canonical_hash = $2,
  canonical_version = canonical_version + ($3::int),  -- 1 if changed, 0 if unchanged
  text_byte_length = $4,
  extractor_version = $5,
  structure = $6,
  metadata = $7,
  status = 'ready',
  updated_at = NOW()
WHERE id = $8
RETURNING canonical_version
```

9. If `canonical_version` incremented: enqueue `remap_highlights`
10. Enqueue `chunk_and_embed_document`

**Success postconditions**:

- `status = 'ready'`
- `canonical_text`, `structure`, `metadata` populated
- `canonical_version` possibly incremented
- Downstream jobs enqueued

**Failure postconditions**:

- `status = 'failed'`
- `error_code = 'pdf_extraction_failed' | 'epub_parse_failed' | 'html_extraction_failed' | 'unknown_format'`

**Retry policy**:

- Max attempts: 5
- Backoff: 1m, 2m, 4m, 8m, 16m

#### 7.1.3 Job: `chunk_and_embed_document`

**Inputs**:

```typescript
{
  document_id: UUID,
  chunk_version: string,
  embedding_model: string
}
```

**Preconditions**:

- Document has `status = 'ready'`
- `canonical_text` exists

**Idempotency key**:

```
(document_id, canonical_version, chunk_version, embedding_model)
```

**Execution**:

1. Chunk document per §5.2.1
2. For each chunk:
   - Format embedding text
   - Call embedding API
   - Write to `content_chunks`
3. Update document:

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
- Chunks in `content_chunks` table

**Failure postconditions**:

- `embedding_status = 'failed'`
- `error_code = 'embedding_provider_timeout' | 'embedding_quota_exceeded' | 'chunking_failed'`

**Retry policy**:

- Max attempts: 5
- Backoff: 2m, 4m, 8m, 16m, 32m

#### 7.1.4 Job: `remap_highlights`

See §3.2 for full specification.

**Inputs**:

```typescript
{
  media_type: 'document' | 'episode' | 'video',
  media_id: UUID,
  old_version: string,
  new_version: string
}
```

**Idempotency key**:

```
(media_type, media_id, new_version)
```

**Retry policy**:

- Max attempts: 3
- Backoff: 1m, 5m, 15m

#### 7.1.5 Job: `embed_thought_source`

**Inputs**:

```typescript
{
  object_type: 'annotation' | 'message' | 'conversation_summary',
  object_id: UUID,
  chunk_version: string,
  embedding_model: string
}
```

**Preconditions**:

- Object exists

**Idempotency key**:

```
(object_type, object_id, chunk_version, embedding_model)
```

**Execution**:

1. Load object content
2. Chunk per §5.2.3
3. For each chunk:
   - Format embedding text
   - Embed
   - Write to `thought_chunks`

**Success postconditions**:

- Chunks in `thought_chunks`

**Failure postconditions**:

- Log error (no separate status field on annotations/messages)

**Retry policy**:

- Max attempts: 5
- Backoff: 1m, 2m, 4m, 8m, 16m

#### 7.1.6 Job: `update_conversation_summary`

**Inputs**:

```typescript
{
  conversation_id: UUID
}
```

**Preconditions**:

- Conversation has ≥ 30 messages OR ≥ 10 new messages since last summary

**Idempotency key**:

```
(conversation_id, latest_message_id)
```

**Execution**:

1. Load conversation messages
2. Build summarization prompt:

```
Summarize the following conversation in 2-3 paragraphs, capturing key points, decisions, and context.

{message history}
```

3. Call LLM (GPT-4-turbo)
4. Update conversation:

```sql
UPDATE conversations SET
  summary_state = $1,
  summary_updated_at = NOW()
WHERE id = $2
```

5. Enqueue `embed_thought_source('conversation_summary', conversation_id)`

**Success postconditions**:

- `summary_state` updated
- Summary embedded

**Failure postconditions**:

- Log warning (conversation continues without summary)

**Retry policy**:

- Max attempts: 3
- Backoff: 5m, 15m, 30m

### 7.2 Phase 2+ Job Specifications (Future)

The following jobs are enqueued in Phase 2 onwards and are OUT OF SCOPE for Phase 1:

- `ensure_episode_transcript` — ASR job for podcast/video transcription
- `refresh_podcast_feed` — Podcast RSS feed ingestion
- `chunk_and_embed_episode_transcript` — Chunking episodes/videos
- `chunk_and_embed_video_transcript` — Synonym for above

These jobs follow similar patterns to Phase 1 jobs with appropriate scope and error codes.

### 7.3 State Machines

#### 7.3.1 Document State Machine

**States**:

- `pending`: Created, ingestion not started
- `processing`: Extraction in progress
- `ready`: Canonical text available
- `failed`: Extraction failed

**Transitions**:

```
[create] → pending
pending → processing [ingest_document dequeued]
processing → ready [canonicalize_document success]
processing → failed [canonicalize_document max retries]
failed → pending [user retry]
ready → processing [re-extraction requested]
```

**User-visible behavior**:

| State | UI Display |
|-------|------------|
| pending | "Processing..." spinner |
| processing | "Processing..." spinner |
| ready | Document readable |
| failed | Error banner: "{error_message}. [Retry]" button |

#### 7.3.2 Embedding State Machine

**States** (orthogonal to ingestion status):

- `pending`: Awaiting chunking/embedding
- `ready`: Embeddings in vector store
- `failed`: Embedding failed

**Transitions**:

```
[canonical_text ready] → pending
pending → ready [chunk_and_embed success]
pending → failed [max retries]
failed → pending [admin retry]
```

**User-visible behavior**:

| State | UI Display |
|-------|------------|
| pending | "Indexing for search..." (subtle note) |
| ready | No special indicator (search works) |
| failed | "Search unavailable for this document." |

#### 7.3.3 Highlight State Machine

**States** (implicit, no enum field):

- **valid**: `is_detached = false`, version matches current
- **stale**: Version doesn't match current (remap pending)
- **detached**: `is_detached = true`
- **hidden**: `is_hidden = true`

**Transitions**:

```
[create] → valid
[media version change] → stale
stale → valid [remap success]
stale → detached [remap failure]
[user hides] → hidden
[user unhides] → valid|detached (preserves detachment state)
```

**User-visible rendering**:

| State | Rendering |
|-------|-----------|
| valid | Inline highlight with color |
| stale | Inline highlight, slightly dimmed, "Updating..." tooltip |
| detached | Not inline. Separate "Orphaned Highlights" section. |
| hidden | Not rendered. Retrievable via "Show hidden" filter. |

### 7.4 Job Cancellation and Deletion

#### 7.4.1 Cancellation Semantics

Jobs MAY be cancelled if:

- User deletes the media object mid-pipeline
- Admin manually cancels job

**Cancellation behavior**:

```typescript
async function cancelJob(jobId: string) {
  const job = await jobQueue.getJob(jobId);

  if (!job) {
    throw new Error('Job not found');
  }

  if (job.state === 'completed') {
    // Already done, cannot cancel
    return { cancelled: false, reason: 'already_completed' };
  }

  if (job.state === 'active') {
    // Job is running; mark for abort
    await job.abort();
    // Worker MUST check for abort signal and exit gracefully
  } else {
    // Job is queued; remove from queue
    await job.remove();
  }

  return { cancelled: true };
}
```

**Worker abort handling**:

All job workers MUST check for cancellation periodically:

```typescript
async function canonicalizeDocument(job: Job) {
  if (await job.isCancelled()) {
    throw new JobCancelledError();
  }

  // ... extraction logic ...

  if (await job.isCancelled()) {
    throw new JobCancelledError();
  }

  // ... write results ...
}
```

#### 7.4.2 Deletion Mid-Pipeline

If user deletes a document while `status = 'processing'`:

1. Mark document `deleted_at = NOW()`
2. Cancel all pending jobs for that document
3. Active jobs complete but do not write results (check `deleted_at` before final write)

**Soft delete**:

```sql
ALTER TABLE documents ADD COLUMN deleted_at TIMESTAMPTZ;
```

Queries MUST exclude deleted documents:

```sql
WHERE deleted_at IS NULL
```

Deletion is permanent after 30 days (background cleanup job).

### 7.5 Dead-Letter Queue

#### 7.5.1 DLQ Behavior

After max retries, job moves to dead-letter queue:

```typescript
async function onJobFailed(job: Job) {
  if (job.attemptsMade >= job.opts.maxAttempts) {
    await deadLetterQueue.add({
      original_job: job.toJSON(),
      failure_reason: job.failedReason,
      attempts: job.attemptsMade,
      failed_at: new Date()
    });
  }
}
```

**DLQ retention**: 90 days

**Admin review**:

- Daily digest email if DLQ size > 100
- Dashboard showing DLQ jobs grouped by `error_code`

**Manual retry**:

```typescript
async function retryDLQJob(dlqJobId: string) {
  const dlqJob = await deadLetterQueue.getJob(dlqJobId);
  const originalJob = dlqJob.data.original_job;

  // Re-enqueue with reset retry count
  await originalQueue.add(originalJob.name, originalJob.data, {
    attempts: 0
  });

  await dlqJob.remove();
}
```

---

## 8. Schema Evolution and Migrations

### 8.1 Version Axes

**Extractor version**:

```
documents.extractor_version: string
```

Semantic version of extraction code (e.g., `"2024.11.1"`).

**Canonical version**:

```
documents.canonical_version: uint32
```

Monotonic counter, incremented when canonical text changes.

**Chunk version**:

```
content_chunks.chunk_version: string
thought_chunks.chunk_version: string
metadata_chunks.chunk_version: string
```

Identifies chunking strategy (e.g., `"v1"`, `"v2"`).

**Embedding model**:

```
content_chunks.embedding_model: string
thought_chunks.embedding_model: string
metadata_chunks.embedding_model: string
```

Identifies embedding model (e.g., `"text-embedding-3-small"`, `"text-embedding-3-large"`).

### 8.2 Migration Strategies (Phase 2+)

#### 8.2.1 Re-chunking Migration

**Scenario**: Change chunking strategy from `chunk_version = "v1"` to `"v2"`.

**Strategy**:

1. **Additive phase**:
   - Deploy code that writes chunks with `chunk_version = "v2"` for new documents
   - Existing chunks with `"v1"` remain
2. **Backfill phase**:
   - Background job processes all documents, writes `"v2"` chunks
   - Do NOT delete `"v1"` chunks yet
3. **Dual-read phase**:
   - Retrieval queries both `"v1"` and `"v2"` chunks
   - Deduplicate by `(media_type, media_id, text_start, text_end)`
4. **Deprecation phase** (after 100% backfill complete):
   - Update retrieval to query only `"v2"`
   - Delete `"v1"` chunks

**Timeline**: 2-4 weeks for large datasets.

#### 8.2.2 Re-embedding Migration

**Scenario**: Switch from `embedding_model = "text-embedding-3-small"` to `"text-embedding-3-large"`.

**Strategy**:

1. **New chunks table** (recommended for different dimensions):

```sql
CREATE TABLE content_chunks_v2 (
  -- same schema, different embedding dimension
  embedding vector(3072)  -- larger model
);
```

2. **Backfill**:
   - Background job re-embeds all chunks with new model
   - Write to `content_chunks_v2`
3. **Dual-query phase**:
   - Query both tables, merge results
4. **Cutover**:
   - Rename `content_chunks` → `content_chunks_v1_archive`
   - Rename `content_chunks_v2` → `content_chunks`
5. **Archive deletion**:
   - After 30 days, drop `content_chunks_v1_archive`

**Cost**: Re-embedding is expensive. Budget $500-$5000 depending on corpus size.

#### 8.2.3 Highlight Detachment During Migrations

**Scenario**: Extractor version changes, canonical text differs.

**Behavior**:

1. `canonical_version` increments
2. Remap job runs per §3.2
3. Highlights either remap or detach

**User communication**:

If > 10% of user's highlights detach:

- Send email: "We've updated our document processing. Some highlights could not be automatically updated. [Review]"
- UI banner: "X highlights need attention. [Review orphaned highlights]"

**Manual re-anchoring**:

User can:

1. View detached highlight with old `quote`
2. Search for quote in new canonical text (with fuzzy matching UI)
3. Select new location
4. System updates offsets and clears `is_detached`

### 8.3 Resumable Jobs

All long-running jobs (backfills, migrations) MUST be resumable:

**Pattern**:

```typescript
async function rechunkAllDocuments(chunkVersion: string) {
  const cursor = await loadCursor('rechunk_migration');

  while (true) {
    const batch = await db.query(`
      SELECT id FROM documents
      WHERE id > $1
        AND status = 'ready'
        AND deleted_at IS NULL
      ORDER BY id
      LIMIT 100
    `, [cursor]);

    if (batch.length === 0) break;

    for (const doc of batch) {
      await chunkAndEmbed(doc.id, chunkVersion);
    }

    cursor = batch[batch.length - 1].id;
    await saveCursor('rechunk_migration', cursor);
  }
}
```

**Cursor storage**:

```sql
CREATE TABLE migration_cursors (
  migration_name TEXT PRIMARY KEY,
  cursor_value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 9. Frontend Architecture

### 9.1 Web Frontend

**Framework**: React 18+

**Reader components**:

- **PDF**: pdf.js-based viewer with text layer extraction
  - Highlight creation via pdf.js TextLayer offsets
  - Page-aware rendering with z-index stacking
- **EPUB/HTML**: Custom text reader
  - Canonical text displayed with highlights
  - Byte-offset-based highlight anchoring

**Cross-platform selection library**: `selection.js`

- Converts DOM selections to byte offsets
- Identical behavior across browsers

**Annotation UI**:

- Sidebar panel for highlights and annotations
- Inline annotation editing

### 9.2 Mobile Frontend (React Native)

**Architecture**:

- WebView for document rendering (PDF, EPUB, HTML)
- Native views for playback controls (audio/video)
- Bridge for selection event communication

**PDF handling**:

- WebView running pdf.js (identical to web)
- WebViewBridge transmits selection events to RN

**Transcript handling**:

- Native audio/video player
- Synced transcript view below player
- Time-based navigation

**Selection semantics**:

- Identical to web (WebView uses same `selection.js`)

---

## 10. Error Behavior and Failure Semantics

### 10.1 API Error Responses

#### 10.1.1 Error Schema

```typescript
interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, any>;
    retry_after?: number;  // seconds
  };
}
```

#### 10.1.2 Error Codes

**Authentication**:

- `401 Unauthorized` — `auth_token_missing | auth_token_invalid | auth_token_expired`

**Authorization**:

- `403 Forbidden` — `insufficient_permissions` (only for library admin actions)
- `404 Not Found` — returned for all visibility failures (see §4.3.1)

**Validation**:

- `400 Bad Request` — `invalid_request`
  - Details: `{ field: 'text_start', reason: 'must be non-negative' }`

**Rate limiting**:

- `429 Too Many Requests` — `rate_limit_exceeded`
  - `retry_after: 60`

**Resource state**:

- `409 Conflict` — `ingestion_incomplete | highlight_detached`
  - Message: "Document is still processing. Try again in a few minutes."

**Server errors**:

- `500 Internal Server Error` — `internal_error`
- `503 Service Unavailable` — `retrieval_unavailable`
  - `retry_after: 60`
- `504 Gateway Timeout` — `llm_timeout`

### 10.2 Ingestion Failures

#### 10.2.1 Document Upload Failure

**Error code**: `pdf_extraction_failed | epub_parse_failed | html_extraction_failed | unsupported_format`

**User-visible**:

```
Error: Failed to process document
Reason: The PDF appears to be corrupted or uses an unsupported format.
[Retry] [Upload Different File]
```

**Retry behavior**:

- System retries automatically up to 5 times
- If still failing, user can manually retry
- Manual retry resets retry counter

#### 10.2.2 Embedding Failure

**Error code**: `embedding_quota_exceeded | embedding_provider_timeout`

**User-visible**:

```
Warning: Search indexing delayed
Your document is readable, but search may not include it yet. We'll retry automatically.
```

**Retry behavior**:

- Automatic retries with exponential backoff
- If quota issue, job pauses until daily reset (midnight UTC)

### 10.3 Retrieval Failures

#### 10.3.1 Vector Store Unavailable

**Response**:

```json
{
  "error": {
    "code": "retrieval_unavailable",
    "message": "Search is temporarily unavailable. Please try again in a moment.",
    "retry_after": 60
  }
}
```

**HTTP status**: `503 Service Unavailable`

**Client behavior**:

- Show error toast
- Retry button
- Disable search UI temporarily

#### 10.3.2 Embedding Provider Timeout

**Response**:

```json
{
  "error": {
    "code": "embedding_timeout",
    "message": "Search query took too long to process. Please try again.",
    "retry_after": 5
  }
}
```

**HTTP status**: `504 Gateway Timeout`

**Client behavior**:

- Automatic retry after 5s
- Show "Searching..." spinner

### 10.4 Highlight Creation Failures

#### 10.4.1 Validation Failure

**Scenario**: Backend cannot verify `quote` matches canonical text.

**Response**:

```json
{
  "error": {
    "code": "highlight_validation_failed",
    "message": "Selected text does not match document. The document may have been updated.",
    "details": {
      "expected_quote": "The text that exists in the document",
      "received_quote": "The text you selected"
    }
  }
}
```

**HTTP status**: `400 Bad Request`

**Client behavior**:

- Remove optimistic highlight from UI
- Show error toast: "Highlight failed. Document may have been updated. [Reload]"
- Suggest page reload

#### 10.4.2 Media Not Ready

**Scenario**: User attempts to highlight while document is still processing.

**Response**:

```json
{
  "error": {
    "code": "ingestion_incomplete",
    "message": "Document is still processing. Please wait.",
    "details": {
      "status": "processing",
      "estimated_completion": "2024-11-21T10:05:00Z"
    }
  }
}
```

**HTTP status**: `409 Conflict`

**Client behavior**:

- Disable highlight button while `status != 'ready'`
- Show "Processing..." banner

#### 10.4.3 Detached Highlight Rendering

**Scenario**: Highlight is detached (`is_detached = true`).

**UI behavior**:

- NOT rendered inline
- Shown in separate "Orphaned Highlights" panel:

```
⚠️ Orphaned Highlights

These highlights could not be mapped to the current version of the document.

• "The text that no longer exists" (created 2024-11-15)
  [Hide] [Try to Re-anchor]
```

**Re-anchoring**:

User clicks "Try to Re-anchor":

1. UI shows fuzzy search results for `quote` in current canonical text
2. User selects correct match
3. Backend updates offsets, clears `is_detached`

### 10.5 Conversation Failures

#### 10.5.1 LLM Provider Timeout

**Response**:

```json
{
  "error": {
    "code": "llm_timeout",
    "message": "AI response took too long. Please try again.",
    "retry_after": 10
  }
}
```

**HTTP status**: `504 Gateway Timeout`

**Client behavior**:

- Show message bubble with error icon
- "Response timed out. [Retry]" button
- Retry sends same message

#### 10.5.2 Context Overflow

**Scenario**: User message + context exceeds maximum token limit even after shrinking.

**Response**:

```json
{
  "error": {
    "code": "context_too_large",
    "message": "Your message is too long. Please shorten it or start a new conversation.",
    "details": {
      "max_tokens": 8000,
      "message_tokens": 9500
    }
  }
}
```

**HTTP status**: `400 Bad Request`

**Client behavior**:

- Show error inline in compose box
- Suggest: "Message too long. Try breaking it into multiple messages."

---

## 11. Implementation Phases

### 11.1 Phase 1: Document Core (8-10 weeks)

#### 11.1.1 Deliverables

**Database**:

- Tables: `users`, `documents`, `highlights`, `annotations`, `libraries`, `library_memberships`, `library_media`, `object_library_visibility`
- Indexes per schemas in §2.3, §3.1

**Backend services**:

- `IngestionService`: upload, blob storage, job enqueuing
- `StructuringService`: PDF/EPUB/HTML extraction, canonicalization
- `VisibilityService`: centralized `Visible(U, O)` implementation
- `HighlightService`: CRUD with validation

**Jobs**:

- `ingest_document`
- `canonicalize_document`
- `chunk_and_embed_document`
- `remap_highlights`
- `embed_thought_source`
- `update_conversation_summary`
- Job queue setup (Celery + Redis)
- Retry and DLQ infrastructure

**Web reader**:

- React app with iframe-based document viewer
- `selection.js` library
- Highlight rendering (overlapping spans, z-index stacking)
- Annotation sidebar

**APIs**:

- `POST /documents/upload`
- `POST /documents/from_url`
- `GET /documents/:id`
- `POST /highlights`
- `PUT /highlights/:id` (color, is_hidden only)
- `GET /highlights?media_type=document&media_id=:id`
- `POST /annotations`
- `PUT /annotations/:id`
- `POST /libraries`
- `POST /libraries/:id/members`
- `POST /libraries/:id/media`
- `POST /conversations`
- `POST /conversations/:id/messages`
- `GET /conversations/:id/messages`
- `POST /search`

#### 11.1.2 Acceptance Criteria

- [ ] User can upload a PDF, wait for processing, see `status = 'ready'`
- [ ] User can read PDF in web reader
- [ ] User can create highlight by selecting text
- [ ] Highlight persists and renders correctly on page reload
- [ ] User can add annotation to highlight
- [ ] User can create library, add document to library
- [ ] User can invite member to library
- [ ] Member can see document and create highlights
- [ ] Non-member cannot see document (404 response)
- [ ] Re-upload of same document (minor text change) triggers remap
- [ ] Highlights remap successfully (>90% success rate on test corpus)
- [ ] User can create conversation and send messages
- [ ] LLM responses cite sources from retrieval
- [ ] Search respects visibility (non-visible content never appears)

#### 11.1.3 Quality Bar

**Performance**:

- Document ingestion (PDF, 100 pages): p95 < 30s
- Highlight creation API: p95 < 200ms
- Web reader load (100k chars): p95 < 2s
- Vector search: p95 < 500ms
- LLM response (excluding provider latency): p95 < 2s

**Correctness**:

- Highlight validation test suite: 100% pass
- Remap test suite (10 scenarios): ≥90% remap success, ≤10% detach
- Visibility test suite: 100% pass (no ACL leaks)
- Retrieval ACL filter rate: <30% (efficient overfetch)

### 11.2 Phase 2: Podcasts and Videos (6-8 weeks) — OUT OF SCOPE for Phase 1

### 11.3 Phase 3: Advanced Retrieval and Summaries (6-8 weeks) — OUT OF SCOPE for Phase 1

### 11.4 Phase 4: Hardening (4-6 weeks) — OUT OF SCOPE for Phase 1

---

## 12. Security and Privacy

### 12.1 Threat Model Summary

See §4.4 for full threat model.

**Key guarantees**:

1. No object existence leaks: `Visible(U, O) = false` → 404, never 403
2. No content leaks via retrieval: post-filter enforced
3. No metadata leaks: error messages, counts, timestamps sanitized
4. Constant-time visibility checks (from adversary perspective)

### 12.2 Authentication via Clerk

**Mechanism**: Clerk OIDC + JWT verification

**Token payload**:

```json
{
  "sub": "user_12345",
  "email": "user@example.com",
  "email_verified": true,
  "iat": 1700000000,
  "exp": 1700086400
}
```

**Mapping to database**:

1. Extract `sub` claim from JWT
2. Look up `users.external_user_id` matching `sub`
3. If not found: create new user row with `external_user_id = sub`, `email = email claim`
4. Return `users.id` for authorization

**Expiration**: 24 hours (set by Clerk)

**Refresh**: Clerk handles refresh token flow client-side via SDK

**Account deletion**:

- User initiates deletion in Clerk console
- Clerk disables account, clients must log out
- Backend soft-deletes user data (30-day retention before hard delete)

**No password handling**: All password operations delegated to Clerk

### 12.3 Rate Limiting

**Per-user**:

- API requests: 1000/hour
- Highlight creation: 100/hour
- Document upload: 10/day

**Global**:

- API requests: 100k/hour

**Implementation**: Token bucket algorithm with Redis

**Response**:

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Too many requests. Please slow down.",
    "retry_after": 3600
  }
}
```

### 12.4 Quotas (Phase 2+)

**Per-user ASR**:

- Free tier: 30 minutes/day
- Paid tier: 300 minutes/day

**Per-user embedding**:

- Free tier: 500k tokens/day
- Paid tier: 5M tokens/day

Quota enforcement is OUT OF SCOPE for Phase 1 (no ASR jobs in Phase 1).

---

## 13. Glossary

**Canonical text**: UTF-8 byte array produced by deterministic extraction from unstructured content. Immutable for a given version.

**Byte offset**: Zero-indexed position in UTF-8 encoding of canonical text. All text spans use byte offsets, not character positions.

**Highlight**: Text span anchored to canonical text via byte offsets, with context (prefix/suffix) for remapping.

**Remap**: Process of finding new byte offsets for highlights after canonical text changes.

**Detached highlight**: Highlight for which remap failed. Marked `is_detached = true`. Not rendered inline, but preserved for audit.

**Visibility function** `Visible(U, O)`: Pure function determining whether user `U` can access object `O`. Enforced at all API, retrieval, and LLM boundaries.

**Embedding space**: Disjoint vector stores for different content types: A (content), B (thoughts), C (metadata).

**Chunk version**: Identifier for chunking strategy (e.g., `"v1"`, `"v2"`). Allows re-chunking migrations.

**Embedding model**: Identifier for embedding model (e.g., `"text-embedding-3-small"`). Allows re-embedding migrations.

**Canonical version**: Monotonic counter incremented when document canonical text changes. Triggers highlight remap.

**Transcript hash**: SHA256 of transcript text. Changes trigger highlight remap for episodes/videos.

**Overfetch factor**: Ratio `K' / K` where `K'` is candidates retrieved from vector store and `K` is final result count. Used to compensate for visibility filtering.

**Scope**: Constraint on retrieval search space (per-doc, per-library, my_notes, global).

**Stub**: Partial message object returned when message is private. Contains metadata but not content.

**Dead-letter queue**: Queue for jobs that failed after max retries. Requires manual admin review.

**Idempotency key**: Unique identifier for job inputs. Jobs with same key are deduplicated (run once only).

**Token budget**: Maximum context size for LLM prompt. Enforced via shrinking algorithm when overflow occurs.

---

## 14. Normative References

- **RFC 2119**: Key words for use in RFCs to Indicate Requirement Levels
- **RFC 3986**: Uniform Resource Identifier (URI): Generic Syntax
- **UTF-8**: Unicode Standard, Chapter 2
- **SHA-256**: FIPS 180-4, Secure Hash Standard

---

**End of Specification**

All requirements in this document are NORMATIVE and REQUIRED for conformant implementations.
