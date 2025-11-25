# Media Types & Canonical Text

## 1. Media Type Classification

The system supports three primary media classes in Phase 1:

### 1.1 Documents (PDF, EPUB, HTML)

Digital documents extracted to linear canonical text via deterministic rules:

- **Formats**: PDF, EPUB, HTML/web articles
- **Canonical form**: UTF-8 text with stable byte offsets
- **Structure**: Extracted chapters, sections, headings
- **Highlighting**: Via byte offsets (text anchors for EPUB/HTML) or pdf.js offsets (PDFs)
- **Versioning**: `canonical_version` counter, `extractor_version` string

### 1.2 Episodes (Podcasts with Transcripts)

Podcast episodes with optional transcript text:

- **Audio**: Stored as URL or local blob
- **Transcript**: Generated via ASR (Whisper) or external service
- **Canonical form**: Transcript UTF-8 text + time-aligned segments
- **Highlighting**: Via byte offsets in transcript + time ranges
- **Versioning**: `asr_model_version`, `transcript_hash`

**Phase 1**: OUT OF SCOPE. Basic schema present; actual transcription deferred to Phase 2.

### 1.3 Videos (YouTube, Vimeo, etc. with Transcripts)

Video content with optional transcript text:

- **Video**: Accessed via URL (YouTube, Vimeo, etc.)
- **Transcript**: Platform captions or ASR
- **Canonical form**: Transcript UTF-8 text + time-aligned segments
- **Highlighting**: Via byte offsets in transcript + time ranges
- **Versioning**: `asr_model_version`, `transcript_hash`

**Phase 1**: OUT OF SCOPE. Basic schema present; actual support deferred to Phase 2.

### 1.4 Podcasts (Parent of Episodes)

Podcast metadata container:

- **Title, description, RSS URL**
- **Episodes**: One-to-many relationship
- **User subscription**: Via `subscriptions` table

**Phase 1**: OUT OF SCOPE. Basic schema present; subscription/feed refresh deferred to Phase 2.

---

## 2. Canonical Text and Versioning

### 2.1 Canonicalization Function

For documents, canonicalization is a **pure function**:

```
canonicalize: (raw_blob: bytes, extractor_version: string) → canonical_text: bytes
```

**Invariants**:

- **CANON-1**: `canonicalize(B, V)` MUST produce byte-identical output for identical inputs `(B, V)`
- **CANON-2**: Output MUST be valid UTF-8 with NFC normalization
- **CANON-3**: Output MUST NOT contain null bytes (`0x00`)
- **CANON-4**: Whitespace MUST be normalized:
  - `\r\n` → `\n`
  - Multiple spaces collapsed to single space
  - Paragraph boundaries marked by exactly two `\n` characters
- **CANON-5**: Output MUST preserve text order (no reordering based on layout)

### 2.2 Extraction Environment

To achieve determinism:

- **Extractor code version MUST be pinned** (e.g., `PyMuPDF==1.23.8`, `pypdf==3.17.1`)
- **Python runtime MUST be pinned** (e.g., `python==3.11.6`)
- **All dependencies MUST be locked** via hash-verified requirements file

Changes to any pinned dependency invalidate `canonical_hash` and trigger remap.

### 2.3 Document Extraction Rules

#### 2.3.1 PDF

1. Extract text using **PyMuPDF (fitz)** as the canonical extractor with `layout=False` (linear text)
   - Alternative fallback: `pdfplumber` for compatibility if PyMuPDF fails
2. Remove headers/footers: Discard text appearing identically on ≥3 consecutive pages
3. Remove page numbers: Discard lines matching `^\s*\d+\s*$`
4. Preserve paragraph boundaries via double newline
5. Apply normalization per CANON-4

**Structure extraction**:
- Extract page-level text boundaries
- Identify major text breaks (> 2 consecutive blank lines) as "sections"

#### 2.3.2 EPUB

1. Parse spine order from `content.opf` (not alphabetical order)
2. Extract text from XHTML documents in spine order
3. Convert block elements (`<p>`, `<div>`, `<h1>`..`<h6>`) to text with paragraph separators
4. Strip inline markup (`<em>`, `<strong>`, etc.)
5. Apply normalization

**Structure extraction**:
- Track `<h1>...<h6>` hierarchy
- Map chapter/section boundaries to text offsets
- Extract Table of Contents (NCX or HTML5 nav)
- Preserve internal anchors and external links

**Stored in `structure_json` field** (see §4.4 below)

#### 2.3.3 HTML (Web Articles)

1. Apply Readability.js extraction (remove nav, ads, sidebars)
2. Extract `textContent` from article node (recursive, depth-first)
3. Strip `<script>`, `<style>`, `<nav>`, elements with `role="complementary"`
4. Apply normalization

**Structure extraction**:
- Extract title (`<h1>` or `<title>`)
- Identify sections via `<h2>`, `<h3>` headings
- Map to text offsets

### 2.4 Transcript Extraction Rules

For transcripts (episodes, videos), canonicalization includes both text and time-alignment:

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

**ASR Normalization**:

1. Concatenate segment texts with single space separators
2. Apply CANON-4 normalization
3. Compute byte offsets for each segment in normalized text
4. Store as `transcript_segments` JSONB array

**Non-determinism Tolerance**:

ASR providers MAY produce different outputs for identical audio. This is tolerated via `transcript_hash` comparison (see §2.5).

---

## 3. Content Hashing Model

### 3.1 Hash Definitions

#### 3.1.1 `content_hash` (Documents, Episodes, Videos)

```
content_hash = SHA256(raw_blob)
```

Identifies the raw input. Change detection: re-upload of identical file produces same hash.

#### 3.1.2 `canonical_hash` (Documents)

```
canonical_hash = SHA256(canonical_text)
```

Identifies the extracted text after canonicalization. Updated whenever canonical text changes.

#### 3.1.3 `anchored_content_hash` (Highlights on Documents)

```
anchored_content_hash = SHA256(canonical_text_at_anchor_creation)
```

Stored in highlight at creation. Used to detect when canonical text changed: triggers remap if `anchored_content_hash != current canonical_hash`.

#### 3.1.4 `transcript_hash` (Episodes, Videos)

```
transcript_hash = SHA256(transcript_text)
```

Identifies transcript output. Updated whenever transcript changes.

#### 3.1.5 `anchored_transcript_hash` (Highlights on Episodes/Videos)

```
anchored_transcript_hash = SHA256(transcript_text_at_anchor_creation)
```

Stored in highlight at creation. Used to detect when transcript changed: triggers remap if `anchored_transcript_hash != current transcript_hash`.

#### 3.1.6 `pdf_file_hash` (PDF Documents)

```
pdf_file_hash = SHA256(raw_pdf_blob)
```

Stored in highlights. Used to trigger remap ONLY if PDF binary changes (not extraction code changes).

### 3.2 Immutability Guarantee

**Critical invariant**: The system stores **only one canonical text per media item at any time**. There is NO version integer counter. When content changes:

1. Old `canonical_text` / `transcript_text` is replaced
2. New hash is computed
3. Highlights store their **anchored hash** from creation time
4. Remap is triggered if anchored hash != new hash

**Consequence**: Historical replay of old content versions is NOT supported. Users cannot "revert" to old text versions; re-upload creates new content.

### 3.3 Extraction Versioning

Changes to extraction code are tracked separately from content versioning:

```python
EXTRACTOR_VERSION = "2024.11.1"   # Tracks extraction code, not content version
```

When extraction code changes:
- New documents use new version
- Old documents retain old version in `extractor_version` field
- Re-extraction of old documents can trigger hash change if output differs
- **Anchors are NOT invalidated by extraction code changes alone** (only by hash changes)

---

## 4. Storage Schema (Overview)

See [spec/schemas/documents.md](schemas/documents.md) for complete schema definitions.

### 4.1 Documents Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK | Owner |
| `title` | TEXT | Extracted or provided |
| `canonical_text` | TEXT | UTF-8 bytes, immutable after extraction |
| `canonical_hash` | TEXT | SHA256 of canonical_text |
| `extractor_version` | TEXT | Version of extraction code (for re-extraction tracking) |
| `structure` | JSONB | Section hierarchy, offsets |
| `status` | ENUM | pending, processing, ready, failed |

### 4.2 Episodes Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `podcast_id` | UUID FK | Parent podcast |
| `user_id` | UUID FK | Who added it |
| `transcript_text` | TEXT | Phase 2+ |
| `transcript_hash` | TEXT | SHA256 of transcript_text |
| `transcript_segments` | JSONB | Segment array with time ranges |
| `asr_model_version` | TEXT | Whisper version, etc. |
| `transcript_status` | ENUM | pending, processing, ready, failed |

### 4.3 Videos Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK | Who added it |
| `source_url` | TEXT UNIQUE | YouTube, Vimeo, etc. |
| `transcript_text` | TEXT | Phase 2+ |
| `transcript_hash` | TEXT | SHA256 of transcript_text |
| `transcript_segments` | JSONB | Segment array with time ranges |
| `transcript_status` | ENUM | pending, processing, ready, failed |

---

## 4.4 EPUB Rendering: Our Typography + Structure Preserved

EPUB documents are rendered using the system's unified reader typography and styling:

### 4.4.1 Publisher CSS NOT Preserved

- **Publisher CSS is NOT rewritten or preserved** in Phase 1
- All EPUB stylesheets are discarded during extraction
- EPUB content is rendered using the application's built-in reader CSS

**Rationale**: Publisher CSS varies widely, may break layout, and complicates maintenance. The system provides a consistent, accessible reading experience.

### 4.4.2 Structure IS Preserved

The system **preserves and maintains structural integrity**:

- Table of Contents (TOC) from EPUB manifest
- Heading hierarchy (`<h1>` through `<h6>`)
- Chapter and section boundaries
- Internal anchors and cross-references
- Page breaks (stored as metadata, not rendered)

### 4.4.3 Rendering Pipeline

```
EPUB extraction:
  1. Extract canonical text (per §2.3.2)
  2. Extract structure_json (sections, headings, TOC, anchors)
  3. Sanitize any HTML fragments (see §4.6)

Frontend rendering:
  1. Fetch canonical_text + structure_json from API
  2. Apply sanitization (if not already done backend)
  3. Render in .reader-root container with scoped reader CSS
  4. Use structure_json to build TOC, navigation
```

### 4.4.4 No Shadow DOM or iframes in Phase 1

- EPUB content rendered directly in the DOM (not shadow DOM)
- No iframe sandboxing in Phase 1
- All content subject to global XSS protections (see §4.6)

### 4.4.5 Structural Preservation: `structure_json`

EPUB documents MUST extract and preserve structural information in `structure_json` JSONB field:

```json
{
  "sections": [
    {
      "id": "sec_01",
      "title": "Introduction",
      "level": 1,
      "text_start": 0,
      "text_end": 532,
      "href": "Text/intro.xhtml#section1"
    },
    {
      "id": "sec_02",
      "title": "Chapter 1: Foundations",
      "level": 1,
      "text_start": 532,
      "text_end": 5240,
      "href": "Text/chapter1.xhtml"
    },
    {
      "id": "sec_02_01",
      "title": "1.1 Background",
      "level": 2,
      "text_start": 890,
      "text_end": 2100,
      "href": "Text/chapter1.xhtml#sec1_1"
    }
  ],
  "toc": [
    {
      "title": "Introduction",
      "section_id": "sec_01",
      "children": []
    },
    {
      "title": "Chapter 1: Foundations",
      "section_id": "sec_02",
      "children": [
        {
          "title": "1.1 Background",
          "section_id": "sec_02_01"
        }
      ]
    }
  ]
}
```

**Extracted fields**:
- `sections[]`: List of headings/sections with text byte offsets, hierarchy level, and original HREF
- `toc[]`: Table of Contents structure (NCX or HTML5 nav.xhtml)
- `level`: Heading level (1-6 for h1-h6)
- `text_start`, `text_end`: Byte offsets in canonical_text
- `href`: Original internal XHTML reference (for forward compatibility)

**Navigation semantics**: Reader uses sections and TOC for chapter/section navigation. Highlights always anchor to canonical text offsets (unchanged).

---

## 4.6 HTML Sanitization for Web Articles & EPUB

All HTML content from web articles and EPUB documents MUST be sanitized before storage and rendering.

### 4.6.1 Sanitization Rules

See [spec/architecture.md §5.1](architecture.md#51-sanitization-ruleset) for complete sanitization rules.

**Summary**:

- **Allowed tags**: `p, h1–h6, em, strong, a, ul, ol, li, code, pre, blockquote, span, div`
- **Disallowed**: `<script>, <style>, <iframe>, <form>, <input>, on* attributes, <object>, <embed>`
- **Implementation**: Bleach (Python) or equivalent allowlist-based sanitizer
- **Timing**: Applied during canonicalization (backend) before storage

### 4.6.2 Sanitization Applied To

1. **Web articles (HTML)**: Readability-extracted content sanitized before storage
2. **EPUB HTML fragments**: If structure_json includes sanitized HTML snippets, they must be cleaned
3. **Rendered markdown**: Markdown → HTML output sanitized (see frontend spec)

### 4.6.3 Example Sanitization

**Input HTML**:

```html
<p>Read this <strong>important</strong> article with <a href="javascript:void(0)" onclick="hack()">link</a></p>
<script>alert('XSS')</script>
<iframe src="evil.com"></iframe>
```

**Output (sanitized)**:

```html
<p>Read this <strong>important</strong> article with <a href="">link</a></p>
```

---

## 5. Critical Invariants

**INV-1**: Canonical text is immutable and singular. The system stores only ONE `canonical_text` per media item at any time. Updates replace the old text entirely; there is no version history.

**INV-2**: Hash equality determines remap triggers:
- For documents: Remap triggered if `anchored_content_hash != current canonical_hash`
- For episodes/videos: Remap triggered if `anchored_transcript_hash != current transcript_hash`
- For PDFs: Remap triggered if `pdf_file_hash` differs (not by extraction code changes)

**INV-3**: Highlights store their anchored hash at creation time. This hash is compared against current media hash to detect staleness.

**INV-4**: PDF anchors use pdf.js offsets (not canonical text byte offsets), so extraction code changes do not affect them. Only PDF file binary changes trigger remap.

**INV-5**: Segment boundaries in transcripts partition the text without gaps or overlaps. This MUST be validated during transcription and remap.

