# Embeddings, Chunking & Retrieval

## 1. Overview

The system maintains three disjoint embedding spaces for semantic search:

1. **Content** (documents, transcripts): Main source material
2. **Thoughts** (annotations, messages, summaries): User's own thinking
3. **Metadata** (titles, descriptions): Structured overview

Each space has independent chunking, embedding models, and vector indices.

---

## 2. Chunking Strategy

### 2.1 Document Chunking

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
CHUNK_OVERLAP = 400  # ~100 tokens, 25% overlap
```

**Embedding text format**:

```
Title: {document.title}
Author: {document.author}
Section: {section_title}

{chunk_text}
```

**Metadata stored**:

```json
{
  "document_id": "uuid",
  "section_title": "Chapter 1: Overview",
  "page_number": 3
}
```

### 2.2 Transcript Chunking

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

TIME_WINDOW = 30.0  # seconds, ~150-200 tokens
OVERLAP_SEGMENTS = 2  # ~5 seconds overlap
```

**Embedding text format**:

```
{podcast_title} - {episode_title}
Timestamp: {time_start}s - {time_end}s

{chunk_text}
```

**Metadata stored**:

```json
{
  "episode_id": "uuid",
  "time_start": 45.3,
  "time_end": 75.8
}
```

### 2.3 Thought Chunking

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

### 2.4 Metadata Chunking

**Titles and descriptions**:

```
{document.title}

Author: {document.author}
Description: {document.metadata.description}
```

**Episode metadata**:

```
{podcast.title} - {episode.title}

{episode.description}
```

**Video metadata**:

```
{video.title}

Channel: {video.channel}
Description: {video.metadata.description}
```

---

## 3. Embedding Spaces

### 3.1 Space A: Content Chunks

**Sources**:

- Document `canonical_text`
- Episode `transcript_text` (Phase 2+)
- Video `transcript_text` (Phase 2+)

**Schema**: See [spec/schemas/chunks.md](schemas/chunks.md)

**Embedding model**: OpenAI `text-embedding-3-small` (default, configurable per space)

**Vector dimension**: 1536 (small) or 3072 (large)

**Index**: IVFFlat with 100 lists

**Use case**: Primary semantic search over documents and transcripts

### 3.2 Space B: Thought Chunks

**Sources**:

- Annotations (highlights + notes)
- Messages (conversation)
- Conversation summaries

**Schema**: See [spec/schemas/chunks.md](schemas/chunks.md)

**Embedding model**: Same as content (configurable)

**Use case**: Find related thoughts, similar discussions, past notes

**Special behavior**: Weighted higher in retrieval (boost factor 1.1)

### 3.3 Space C: Metadata Chunks

**Sources**:

- Document titles, authors, descriptions
- Podcast/episode titles, descriptions
- Video titles, channels

**Schema**: See [spec/schemas/chunks.md](schemas/chunks.md)

**Embedding model**: Same as content (configurable)

**Use case**: Find documents by description, discover new sources

**Special behavior**: Weighted lower in retrieval (boost factor 0.9)

---

## 4. Retrieval Contracts

### 4.1 Retrieval Request

```typescript
interface RetrievalRequest {
  query: string;                          // User query
  scope: RetrievalScope;                  // 'global' or specific library
  spaces: ('content' | 'thought' | 'metadata')[];  // Which spaces to search
  k: number;                              // Number of results desired
  user_id: UUID;                          // From auth context
}

type RetrievalScope =
  | { type: 'global' }
  | { type: 'library'; library_id: UUID }
```

### 4.2 Retrieval Response

```typescript
interface RetrievalResponse {
  results: RetrievalResult[];
  warnings?: string[];

  searchTokens?: number;                  // For budget tracking
}

interface RetrievalResult {
  id: UUID;                               // Chunk ID
  chunk_type: 'content' | 'thought' | 'metadata';

  source_type: 'document' | 'episode' | 'video' | 'annotation' | 'message';
  source_id: UUID;

  text: string;                           // Chunk text
  similarity: number;                     // [0, 1] cosine similarity

  metadata: {
    title: string;
    section_title?: string;
    time_start?: number;
    time_end?: number;
    author?: string;
  };
}
```

### 4.3 Retrieval Algorithm

```typescript
async function retrieve(request: RetrievalRequest): Promise<RetrievalResponse> {
  // 1. Embed query
  const queryEmbedding = await embed(request.query);

  // 2. Search each space
  const contentResults = request.spaces.includes('content')
    ? await searchContentChunks(queryEmbedding, request.scope, request.k * 3)
    : [];

  const thoughtResults = request.spaces.includes('thought')
    ? await searchThoughtChunks(queryEmbedding, request.user_id, request.k * 3)
    : [];

  const metadataResults = request.spaces.includes('metadata')
    ? await searchMetadataChunks(queryEmbedding, request.scope, request.k * 3)
    : [];

  // 3. Combine and filter by visibility
  const allCandidates = [
    ...contentResults.map(r => ({ ...r, space: 'content' })),
    ...thoughtResults.map(r => ({ ...r, space: 'thought' })),
    ...metadataResults.map(r => ({ ...r, space: 'metadata' }))
  ];

  // 4. Post-filter: only include visible results
  const visibleCandidates = [];
  for (const candidate of allCandidates) {
    const source = await loadSourceObject(candidate.source_type, candidate.source_id);
    if (await isVisible(request.user_id, source)) {
      visibleCandidates.push(candidate);
    }
  }

  // 5. Re-rank by weighted similarity
  const weighted = visibleCandidates.map(r => ({
    ...r,
    weighted_similarity: r.similarity * getSpaceWeight(r.space)
  }));

  weighted.sort((a, b) => b.weighted_similarity - a.weighted_similarity);

  // 6. Return top k
  return {
    results: weighted.slice(0, request.k).map(r => ({
      ...r,
      similarity: r.weighted_similarity
    }))
  };
}

function getSpaceWeight(space: 'content' | 'thought' | 'metadata'): number {
  switch (space) {
    case 'content': return 1.0;
    case 'thought': return 1.1;    // boost user's own thoughts
    case 'metadata': return 0.9;
  }
}
```

### 4.4 ACL Enforcement

**Overfetch strategy**:

1. Fetch 3x more results from vector store than needed (k * 3)
2. Filter by `Visible(user, source_object)` at application layer
3. Re-rank and return top k visible results

**Why application-layer filtering?**

- Vector store cannot evaluate `Visible(U, O)` function
- Prevents timing side-channels (constant query cost regardless of visibility)
- Defense in depth: double-check visibility in LLM context assembly

See [spec/acl.md](acl.md) §3.2 for full ACL enforcement details.

### 4.5 Failure Semantics

**Vector store unreachable**:

- Return 503 Service Unavailable
- Error message: `"Retrieval service temporarily unavailable"`
- Retry-After header: 60 seconds

**Embedding provider timeout**:

- Timeout: 10 seconds
- Return 504 Gateway Timeout
- Error message: `"Query embedding timeout"`

**Partial results**:

If some vector stores succeed and others fail (e.g., content succeeds but thought fails):

- Return partial results with warning
- Response includes `warnings: string[]` field

```json
{
  "results": [...],
  "warnings": ["Thought search unavailable, showing content results only"]
}
```

---

## 5. Re-embedding & Model Upgrades

### 5.1 Chunking Version Changes

When chunking algorithm changes (e.g., different window size):

1. Bump `chunk_version` (e.g., `"v1"` → `"v2"`)
2. Trigger background job to re-chunk all documents
3. Delete old chunks with `chunk_version = "v1"`
4. Write new chunks with `chunk_version = "v2"`
5. Retrieval searches both versions (union) during transition period

### 5.2 Embedding Model Changes

When embedding model changes (e.g., `text-embedding-3-small` → `text-embedding-3-large`):

1. Keep old embeddings for fallback
2. Generate new embeddings with new model
3. Retrieval queries both indices (union of results, re-ranked)
4. Gradually delete old embeddings after 30-day transition

---

## 6. Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Chunk document | < 5s | Includes embedding API calls |
| Retrieve k=10 | < 500ms | Including post-filter, overfetch 3x |
| Vector index size | < 100 GB | For 1M documents × 10 chunks/doc |
| Query latency (p95) | < 200ms | Vector search only, no filtering |

---

## 7. Cost Optimization

### 7.1 Batch Embedding

Chunk requests batched (up to 100 chunks per API call) to minimize embedding API costs.

### 7.2 Selective Re-embedding

Only re-embed if:

- Document content changed (hash changed)
- Embedding model changed (chunk_version or embedding_model changed)
- Do not re-embed for structure changes, metadata changes, or highlighting

### 7.3 Caching (Phase 2+)

- Cache query embeddings (same query within 5 min)
- Cache retrieval results (same query within 5 min)
- Invalidate on chunk updates

