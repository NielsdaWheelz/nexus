# Schema: Highlights, Annotations, Anchors

## 1. Highlights Table

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

  deleted_at TIMESTAMPTZ,

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

CREATE INDEX idx_highlights_user ON highlights(user_id) WHERE NOT is_hidden AND deleted_at IS NULL;
CREATE INDEX idx_highlights_media ON highlights(media_type, media_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_highlights_anchor_type ON highlights(anchor_type);
CREATE INDEX idx_highlights_pdf ON highlights(media_id, pdf_page_number) WHERE anchor_type = 'pdf' AND deleted_at IS NULL;
CREATE INDEX idx_highlights_transcript ON highlights(media_id, time_start) WHERE anchor_type = 'transcript' AND deleted_at IS NULL;
```

## 2. Annotations Table

```sql
CREATE TABLE annotations (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  highlight_id UUID NOT NULL REFERENCES highlights(id) ON DELETE CASCADE,

  -- Content
  content TEXT NOT NULL,

  -- Visibility
  is_public BOOLEAN NOT NULL DEFAULT FALSE,

  deleted_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_annotations_highlight ON annotations(highlight_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_annotations_user ON annotations(user_id) WHERE deleted_at IS NULL;
```

