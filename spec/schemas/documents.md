# Schema: Documents, Episodes, Videos, Podcasts

## 1. Users Table

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

## 2. Documents Table

```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  author TEXT,
  published_date DATE,
  source_url TEXT,

  -- Original blob (always stored)
  original_blob_key TEXT NOT NULL,
  original_mime_type TEXT NOT NULL,
  original_size_bytes BIGINT NOT NULL,

  -- Raw blob (canonical source)
  content_hash TEXT NOT NULL,

  -- Canonical text
  canonical_text TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,
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

### 2.1 Original Blob Storage Policy

**CRITICAL**: The system MUST ALWAYS store the original blob (in S3 or equivalent) under `original_blob_key`:

**Rationale**:

1. **Reproducibility**: Ability to re-extract with improved extraction code
2. **Bug fixes**: If extraction bugs are discovered, re-process original blobs
3. **User bug reports**: Provide original blob for debugging
4. **Future features**: Add images, figures, or rich media from original source

**Fields**:

- `original_blob_key`: S3 key to original uploaded blob (PDF, EPUB, HTML, etc.)
- `original_mime_type`: MIME type of original (e.g., `application/pdf`, `application/epub+zip`, `text/html`)
- `original_size_bytes`: File size in bytes (for quota tracking and validation)

**Immutability**:

Once set, these three fields MUST NOT change during the lifetime of the document. If a user re-uploads a document, a new document record is created.

**Access Control**:

Users are not granted direct access to original blobs via API. The blobs are purely internal infrastructure. Canonical text is the public interface.

## 3. Podcasts Table (Phase 2+)

```sql
CREATE TABLE podcasts (
  id UUID PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  rss_url TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_podcasts_rss_url ON podcasts(rss_url);
```

## 4. Episodes Table (Phase 2+)

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

## 5. Videos Table (Phase 2+)

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

## 6. Subscriptions Table (Phase 2+)

```sql
CREATE TABLE subscriptions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  podcast_id UUID NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (user_id, podcast_id)
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_podcast ON subscriptions(podcast_id);
```

