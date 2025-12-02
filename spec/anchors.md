# Highlight Anchoring & Remapping

## 1. Highlight Primitive

A **highlight** is a text span anchored to content via byte offsets (or pdf.js offsets for PDFs), with context for disambiguation.

### 1.1 Anchor Type Overview

Highlights use three distinct anchor types depending on media format and rendering requirements:

| Anchor Type | Media Type | Uses | Stability Driver |
|------------|-----------|------|------------------|
| `text` | Document (EPUB/HTML) | Canonical text character offsets (codepoints) | Content hash (anchored_content_hash vs canonical_hash) |
| `pdf` | Document (PDF) | pdf.js text layer offsets | PDF file binary (pdf_file_hash) |
| `transcript` | Episode, Video | Transcript character offsets + time | Transcript hash (anchored_transcript_hash vs transcript_hash) |

### 1.2 Text Anchors (`anchor_type='text'`)

Used for: EPUB documents, web articles, and any canonical text media where character offsets are stable.

**Offset Semantics (v1)**:

text_start and text_end are zero-indexed positions into canonical_text treated as a sequence of Unicode code points. For practical purposes, treat them as Python/JavaScript string indices. This keeps frontend/backend semantically aligned without byte↔codepoint mapping complexity.

Note: This differs from earlier spec drafts that specified UTF-8 byte offsets. The change was made to simplify frontend/backend alignment—JavaScript strings and Python strings both index by code points natively. For ASCII-heavy content (English text), byte and codepoint indices are identical.

**`text_start`, `text_end`**:

- Zero-indexed character positions (codepoint indices) in `canonical_text`
- `[start, end)` interval (inclusive start, exclusive end)
- MUST satisfy: `0 ≤ text_start < text_end ≤ len(canonical_text)`
- In Python: `len(canonical_text)` gives character count
- In JavaScript: `canonicalText.length` gives character count

**`quote`**:

- The exact characters `canonical_text[text_start:text_end]` at creation time
- Maximum length: 10,000 characters
- MUST be validated at creation: `quote == canonical_text[text_start:text_end]`

**`prefix`**:

- Context before quote: `canonical_text[max(0, text_start - 64):text_start]`
- Fixed length: 64 characters (or less if insufficient text)
- If `text_start < 64`, prefix is truncated

**`suffix`**:

- Context after quote: `canonical_text[text_end:min(len(canonical_text), text_end + 64)]`
- Fixed length: 64 characters (or less if insufficient text)
- If `text_end + 64 > len(canonical_text)`, suffix is truncated

**Type-specific fields**: PDF and transcript fields MUST be NULL

**Hash anchor**: `anchored_content_hash` MUST be set to current document's `canonical_hash` at creation

**Canonical text usage**: Used for both highlighting (visual anchor) AND positional anchoring (byte offsets)

### 1.3 PDF Anchors (`anchor_type='pdf'`)

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

**Hash anchor**: `pdf_file_hash` MUST be set at creation. For retrieval consistency, `anchored_content_hash` is also stored.

**Remapping behavior**: PDF highlights are remapped using pdf.js text layer extraction, NOT canonical_text. Remap algorithm searches within pdf.js extracted text for quote + prefix/suffix matches. Remap ONLY occurs if `pdf_file_hash` differs from current PDF file hash.

### 1.4 Transcript Anchors (`anchor_type='transcript'`)

Used for: Episodes and videos where highlights reference transcript text and must support time-based navigation.

**`text_start`, `text_end`**:

- Zero-indexed character positions (codepoint indices) in `transcript_text`
- `[start, end)` interval (inclusive start, exclusive end)
- MUST satisfy: `0 ≤ text_start < text_end ≤ len(transcript_text)`

**`quote`**:

- The exact characters `transcript_text[text_start:text_end]` at creation time
- Maximum length: 10,000 characters
- MUST be validated at creation: `quote == transcript_text[text_start:text_end]`

**`prefix`, `suffix`**:

- Context extracted from `transcript_text` (64 characters each)

**`time_start`, `time_end`** (REQUIRED):

- Floating-point timestamps in seconds (relative to media start)
- Derived from `transcript_segments` JSONB at creation time
- Used for:
  1. Seeking to highlight position in audio/video player
  2. Rendering time-coded links (e.g., "02:34 - 02:47")
  3. Fallback navigation if text remapping fails

**Type-specific fields**: `time_start`, `time_end` MUST be non-NULL; PDF fields MUST be NULL

**Hash anchor**: `anchored_transcript_hash` MUST be set to current transcript's `transcript_hash` at creation

**Remapping behavior**: Transcript highlights are remapped using `transcript_text`. If text remapping fails but `time_start`/`time_end` are still valid (within media duration), highlight MAY be kept as "time-only anchor" with `detached_reason = "text_detached_time_anchor_retained"`.

---

## 2. Anchor Invariants

**HL-1**: At creation, backend MUST verify anchor integrity based on `anchor_type`:

For **text** anchors:
```python
assert canonical_text[text_start:text_end] == quote
assert canonical_text[max(0, text_start - 64):text_start] == prefix
assert canonical_text[text_end:min(len(canonical_text), text_end + 64)] == suffix
assert anchored_content_hash is not None
assert anchored_content_hash == canonical_hash  # At creation time
assert pdf_page_number is None
assert time_start is None
```

For **PDF** anchors:
```python
pdfjs_text = extract_pdfjs_text(media_id)
assert pdfjs_text[text_start:text_end] == quote
assert pdfjs_text[max(0, text_start - 64):text_start] == prefix
assert pdfjs_text[text_end:min(len(pdfjs_text), text_end + 64)] == suffix
assert anchored_content_hash is not None  # For retrieval consistency
assert pdf_page_number is not None
assert pdf_char_offset is not None
assert pdf_file_hash is not None
assert pdf_file_hash == current_pdf_hash  # At creation time
assert time_start is None
```

For **transcript** anchors:
```python
transcript_text = get_transcript_text(media_type, media_id)
assert transcript_text[text_start:text_end] == quote
assert transcript_text[max(0, text_start - 64):text_start] == prefix
assert transcript_text[text_end:min(len(transcript_text), text_end + 64)] == suffix
assert anchored_transcript_hash is not None
assert anchored_transcript_hash == transcript_hash  # At creation time
assert time_start is not None
assert time_end is not None
assert time_end > time_start
assert pdf_page_number is None
media = get_media(media_type, media_id)
assert time_end <= media.duration_seconds
```

**HL-2**: Highlights MAY overlap. Rendering MUST stack overlapping highlights with shortest span on top (highest z-index).

**HL-3**: Highlights store anchored hashes (`anchored_content_hash` or `anchored_transcript_hash`) at creation. When content hash changes, highlights become **stale** and MUST be remapped.

**HL-4**: Detached highlights MUST preserve original `text_start`, `text_end`, `quote` for audit trail. They are not rendered inline but MUST be visible in a separate UI section.

---

## 3. Highlight Remapping

### 3.1 Remap Trigger

A remap job MUST be enqueued when:

1. Document `canonical_hash` changes (different from highlights' `anchored_content_hash`)
2. Episode/video `transcript_hash` changes (different from highlights' `anchored_transcript_hash`)
3. PDF file binary changes (detected via `pdf_file_hash` mismatch)

**Input**:

```
remap_highlights(
  media_type: string,
  media_id: UUID,
  old_hash: string,      # Previous content/transcript/pdf hash
  new_hash: string,      # Current content/transcript/pdf hash
  old_canonical_text: bytes,  (for text anchors only)
  new_canonical_text: bytes   (for text anchors only)
)
```

### 3.2 Remap Algorithm

The remap algorithm dispatches based on `anchor_type`:

#### 3.2.1 Text Anchor Remapping

```python
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
```

**Fuzzy search** (edit distance):

- Compute edit distance for all substrings of length ±20% of quote length
- Threshold: max 10% edit distance
- If match found: update offsets
- If no match: mark detached

#### 3.2.2 PDF Anchor Remapping

```python
def remap_pdf_anchor(H, old_version, new_version):
    """Remap highlights anchored to pdf.js text layer (PDFs only)."""
    # Check if PDF file has changed via file hash
    new_pdf_hash = get_pdf_file_hash(H.media_id)

    if new_pdf_hash == H.pdf_file_hash:
        # PDF binary unchanged; no remap needed
        return "pdf_unchanged"

    # Extract pdf.js text layer for new version
    pdfjs_text_new = extract_pdfjs_text(H.media_id, version=new_version)

    # Same algorithm as text anchoring, but on pdf.js text layer
    # (exact match → disambiguation → fuzzy)

    # ... [similar to text remapping, but against pdfjs_text_new] ...

    return update_pdf_offsets(H, new_start, pdfjs_text_new, new_version, new_pdf_hash)
```

**Key difference**: Remap only triggers if `pdf_file_hash` differs. Extraction code changes do not trigger PDF remaps.

#### 3.2.3 Transcript Anchor Remapping

```python
def remap_transcript_anchor(H, old_hash, new_hash):
    """Remap highlights anchored to transcript_text (episodes, videos)."""
    T_old = get_transcript_text(H.media_type, H.media_id, hash=old_hash)
    T_new = get_transcript_text(H.media_type, H.media_id, hash=new_hash)

    # Same algorithm as text anchoring
    # ... [exact match → disambiguation → fuzzy] ...

    # Special fallback: if text mapping fails but time is valid
    media = get_media(H.media_type, H.media_id)
    if H.time_end <= media.duration_seconds:
        # Keep as time-only anchor (text detached but time valid)
        return mark_time_only_anchor(H, new_hash)

    # Both text and time invalid
    return mark_detached(H, "transcript_text_and_time_invalid")
```

**Fallback**: If text remapping fails but time range is still valid, retain the highlight as a "time-only anchor" for audio/video seeking.

### 3.3 Remap Job Specification

**Job name**: `remap_highlights`

**Inputs**:

```typescript
{
  media_type: string,
  media_id: UUID,
  old_hash: string,      # Previous hash
  new_hash: string       # Current hash
}
```

**Preconditions**:

- Media exists with new hash
- Highlights exist with old hash

**Idempotency key**:

```
(media_type, media_id, new_hash)
```

If all highlights already reference `new_hash`, skip job.

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

### 3.4 Concurrency

Remap jobs MUST acquire row-level locks to prevent concurrent updates:

```sql
SELECT * FROM highlights
WHERE media_type = :media_type AND media_id = :media_id
  AND (anchored_content_hash = :old_hash OR anchored_transcript_hash = :old_hash OR pdf_file_hash = :old_hash)
FOR UPDATE
```

This ensures atomicity when updating offsets and hash anchors.

---

## 4. Mutable Fields

Only the following fields MAY be mutated after highlight creation:

- `color`: Highlight color (yellow, blue, green, pink, purple)
- `is_hidden`: User-hidden (not rendered, but retained)
- `is_public`: Explicit sharing flag
- `is_detached`: Set by remap algorithm or manual override
- `detached_reason`: Explanation for detachment

All other fields (offsets, quote, prefix/suffix, anchor type, version) are **immutable**.

---

## 5. User-Visible Highlight States

| State | Rendering | Notes |
|-------|-----------|-------|
| **Valid** | Inline highlight with user color | `is_detached=false`, version matches current |
| **Stale** | Dimmed inline, "Updating..." tooltip | Version mismatch, remap pending (< 1s) |
| **Detached** | Separate "Orphaned Highlights" section | `is_detached=true`, text/time not found |
| **Hidden** | Not rendered | `is_hidden=true`, retrievable via "Show hidden" filter |

