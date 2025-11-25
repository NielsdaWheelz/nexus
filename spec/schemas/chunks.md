# Schema: Content Chunks, Thought Chunks, Metadata Chunks

## 1. Content Chunks Table

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

```json
{
  "document_id": "uuid",
  "section_title": "Chapter 1: Overview",
  "page_number": 3,
  "time_start": 45.3,
  "time_end": 75.8
}
```

## 2. Thought Chunks Table

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

```json
{
  "annotation_id": "uuid",
  "highlight_id": "uuid",
  "media_type": "document",
  "media_id": "uuid",
  "conversation_id": "uuid",
  "message_id": "uuid"
}
```

## 3. Metadata Chunks Table

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

**Metadata fields**:

```json
{
  "title": "Document or Episode Title",
  "author": "Author Name",
  "channel": "YouTube Channel",
  "description": "Brief description"
}
```

---

## 4. Chunk Management

### 4.1 Chunk Creation

Chunks are created by background jobs:

- `chunk_and_embed_document`: Creates content chunks for documents
- `chunk_and_embed_episode_transcript`: Creates content chunks for episodes (Phase 2)
- `chunk_and_embed_video_transcript`: Creates content chunks for videos (Phase 2)
- `embed_thought_source`: Creates thought chunks for annotations, messages, summaries
- (Metadata chunks auto-created when documents/episodes/videos ingested)

### 4.2 Chunk Deletion

Chunks are deleted when:

1. Source media is deleted: CASCADE delete via FK reference
2. Embedding model upgraded: Background job deletes old chunks, creates new ones
3. Chunking strategy changed: Old chunks deleted, new chunks created

### 4.3 Chunk Versioning

Chunks stored with version identifiers:

```sql
chunk_version TEXT NOT NULL,     -- e.g., "v1", "v2"
embedding_model TEXT NOT NULL,   -- e.g., "text-embedding-3-small"
```

Multiple versions can coexist during migration period. Retrieval queries all versions (union), re-ranked by freshness.

---

## 5. Retrieval Queries

### 5.1 Similarity Search

```sql
SELECT *
FROM content_chunks
WHERE media_type = 'document'
  AND (embedding <=> ?embedding) < 0.3  -- cosine distance
ORDER BY embedding <-> ?embedding  -- closest first
LIMIT ?k * 3;
```

### 5.2 Bulk Visibility Filter

```sql
-- Load chunks, then in application:
visible_chunks = []
for chunk in chunks:
    source = load_source(chunk.media_type, chunk.media_id)
    if Visible(user, source):
        visible_chunks.append(chunk)
```

### 5.3 Post-filtering by Token Budget

```python
def filter_by_budget(chunks, budget_tokens):
    """Keep chunks within token budget."""
    filtered = []
    total = 0
    for chunk in chunks:
        tokens = count_tokens(chunk.text)
        if total + tokens > budget_tokens:
            break
        filtered.append(chunk)
        total += tokens
    return filtered
```

