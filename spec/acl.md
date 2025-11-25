# Access Control & Visibility Model

## 1. Visibility Function

All access control is governed by a single pure function:

```
Visible(U: UUID, O: Object) → bool
```

Where:

- `U` is a user ID
- `O` is any entity (document, episode, video, highlight, annotation, conversation, message)

The function determines whether user `U` can see/access object `O`.

---

## 2. Visibility Rules by Object Type

### 2.1 Media Visibility

#### Documents

```sql
Visible(U, document D) :=
  EXISTS (
    SELECT 1 FROM library_memberships lm
    JOIN library_media lmed ON lm.library_id = lmed.library_id
    WHERE lm.user_id = U
      AND lmed.media_type = 'document'
      AND lmed.media_id = D.id
      AND D.deleted_at IS NULL
  )
```

Document is visible if user is a member of any library containing it.

#### Episodes (Phase 2+)

```sql
Visible(U, episode E) :=
  EXISTS (
    SELECT 1 FROM subscriptions s
    WHERE s.user_id = U
      AND s.podcast_id = E.podcast_id
      AND E.deleted_at IS NULL
  )
```

Episode is visible if user is subscribed to the podcast.

#### Videos

```sql
Visible(U, video V) :=
  EXISTS (
    SELECT 1 FROM library_memberships lm
    JOIN library_media lmed ON lm.library_id = lmed.library_id
    WHERE lm.user_id = U
      AND lmed.media_type = 'video'
      AND lmed.media_id = V.id
      AND V.deleted_at IS NULL
  )
```

Video is visible if user is a member of any library containing it.

### 2.2 User-Owned Objects

#### Highlights

```sql
Visible(U, highlight H) :=
  Visible(U, media_of(H))  -- underlying media MUST be visible
  AND
  (
    (H.user_id = U)  -- owner always sees own
    OR
    (H.is_public = TRUE)  -- public highlights visible to all
    OR
    EXISTS (  -- shared into accessible library
      SELECT 1 FROM object_library_visibility olv
      JOIN library_memberships lm ON olv.library_id = lm.library_id
      WHERE olv.object_type = 'highlight'
        AND olv.object_id = H.id
        AND lm.user_id = U
    )
  )
  AND H.deleted_at IS NULL
```

Highlight is visible if:

1. Underlying media is visible, AND
2. User is owner, OR highlight is public, OR highlight is shared to user's library

#### Annotations

```sql
Visible(U, annotation A) :=
  Visible(U, highlight_of(A))
  AND A.deleted_at IS NULL
```

Annotation is visible if its highlight is visible.

#### Conversations

```sql
Visible(U, conversation C) :=
  (
    (C.user_id = U)  -- owner
    OR
    (C.is_public = TRUE)  -- public
    OR
    EXISTS (  -- shared into accessible library
      SELECT 1 FROM object_library_visibility olv
      JOIN library_memberships lm ON olv.library_id = lm.library_id
      WHERE olv.object_type = 'conversation'
        AND olv.object_id = C.id
        AND lm.user_id = U
    )
  )
  AND C.deleted_at IS NULL
```

Conversation is visible if user is owner, it's public, or it's shared to user's library.

#### Messages

```sql
Visible(U, message M) :=
  Visible(U, conversation_of(M))  -- conversation must be visible
  AND
  (
    (M.user_id = U)  -- owner
    OR
    (M.is_public = TRUE AND Visible(U, conversation_of(M)))  -- public message in visible conversation
    OR
    EXISTS (  -- shared into accessible library
      SELECT 1 FROM object_library_visibility olv
      JOIN library_memberships lm ON olv.library_id = lm.library_id
      WHERE olv.object_type = 'message'
        AND olv.object_id = M.id
        AND lm.user_id = U
        AND Visible(U, conversation_of(M))
    )
  )
  AND M.deleted_at IS NULL
```

Message is visible if conversation is visible AND user is owner/message is public/message is shared.

### 2.3 Private Message Stubs

If `Visible(U, conversation C)` is true but `Visible(U, message M in C)` is false, the API MUST return a **message stub**:

```json
{
  "id": "msg_uuid",
  "conversation_id": "conv_uuid",
  "role": "user",
  "content": "[Private message]",
  "created_at": "2024-11-21T10:00:00Z",
  "is_stub": true
}
```

**Metadata leaked**:
- `id`, `conversation_id`, `role`, `created_at`, `is_stub`
- Content, model, `effective_model_id`, embeddings MUST be omitted

**Rationale**: User can see they have private messages from specific roles at specific times, but not the content (useful for conversation awareness without privacy breach).

### 2.4 Links

Links are **not independently visible** resources. They are only returned while traversing from a visible object:

```sql
Visible(U, link L) :=
  Visible(U, source_of(L)) AND Visible(U, target_of(L))
```

When resolving links for object `O` as user `U`:

- Load all links where `source = O` or `target = O`
- Filter to only links where both `source` and `target` are visible to `U`
- Never leak the existence of invisible endpoint objects

---

## 3. Enforcement Points

### 3.1 API Layer

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

**Rationale for 404**: Returning 403 Forbidden leaks that the object exists. 404 (Not Found) is indistinguishable from the object never existing.

### 3.2 Retrieval Layer

Vector search MUST post-filter all candidates at application layer:

```typescript
async function vectorSearch(
  userId: UUID,
  query: string,
  k: number
): Promise<Chunk[]> {
  const embedding = await embed(query);

  // Overfetch: request 3x results to account for filtering
  const candidates = await vectorStore.search(embedding, k * 3);

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

**Why application-layer filtering?**

- Vector store (pgvector) cannot evaluate `Visible(U, O)` function
- Prevents timing side-channels (query takes same time regardless of visibility)
- Allows for complex visibility logic without overcomplicating vector queries

### 3.3 LLM Context Layer

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

**Defense in depth**: Even if retrieval layer is compromised, LLM never sees invisible content.

---

## 4. Threat Model

### 4.1 Adversary Capabilities

**Assumed adversary**:

- Authenticated user with valid account
- Can make arbitrary API requests within rate limits
- Can inspect all client-side code (web/mobile)
- Cannot access database directly
- Cannot intercept other users' TLS traffic
- Cannot forge JWTs (Clerk JWKS verification)

**Attack vectors**:

1. Direct object access (guessing UUIDs, enumerating IDs)
2. Retrieval overfetch inspection (inferring existence via vector search timing)
3. Link graph traversal (following references to invisible objects)
4. Metadata leaks (timestamps, counts, error messages revealing invisible data)
5. Timing attacks (request latency varies based on invisible data)
6. Batch operations (listing, filtering on invisible sets)

### 4.2 Security Guarantees

**G-1**: An adversary MUST NOT learn the existence of objects for which `Visible(U, O) = false`

**G-2**: API responses MUST NOT leak:

- Object IDs of invisible objects
- Content snippets of invisible objects
- Embeddings of invisible objects
- Counts of invisible objects (e.g., "5 more private messages")
- Timestamps of invisible objects (except for message stubs as specified in §2.3)
- Metadata of invisible objects (titles, authors, descriptions)

**G-3**: Retrieval timing MUST NOT leak invisible object existence:

- Vector search executes in constant time (from adversary perspective)
- Post-filtering happens in application layer, not database
- Overfetch strategy ensures k visible results always returned (no timing difference for "found fewer than k")

**G-4**: Error messages MUST NOT distinguish between "object does not exist" and "object exists but you cannot access it"

- Use 404 for both cases
- Use generic error messages ("Not found")
- Do not include object type, ID, or other metadata in error

### 4.3 Acceptable Metadata Leaks

The following metadata leaks are **acceptable**:

- **Private message stubs**: Reveal existence, timestamp, author ID, role (see §2.3)
  - Rationale: User can see their conversation contains private messages from others, but not content
- **Deleted object metadata**: Creation timestamp in audit logs (30-day retention)
  - Rationale: Audit trail must show when things existed, only for account owners

The following metadata leaks are **forbidden**:

- Chunk embeddings of invisible content in vector store responses
- Mention of invisible object IDs in link traversal
- Retrieval result counts that change based on invisible content (e.g., "1 of 5 results")
- Error messages that reveal object existence (e.g., "User 123 is not a member")
- Cache timing leaks (database query caches must be keyed by (user_id, object_id))

---

## 5. Implementation Checklist

### 5.1 API Endpoints

- [ ] All list endpoints filter by `Visible(U, O)`
- [ ] All get endpoints return 404 (not 403) on visibility check failure
- [ ] All create endpoints check `Visible(U, parent_object)` before allowing creation
- [ ] All update/delete endpoints check `Visible(U, O)` and ownership
- [ ] No endpoint returns count of invisible objects
- [ ] No endpoint returns list of invisible objects in error messages

### 5.2 Database Queries

- [ ] All `SELECT` queries include `WHERE deleted_at IS NULL`
- [ ] All visibility checks use JOIN patterns from §2, not application logic
- [ ] No "leak" of IDs in error logging (sanitize error messages)
- [ ] Row-level locks (FOR UPDATE) held for consistency in mutations

### 5.3 Retrieval & Embeddings

- [ ] Vector search fetches 3x results (overfetch)
- [ ] Post-filter at application layer before returning
- [ ] Defense-in-depth check in LLM context assembly
- [ ] Retrieval never includes embeddings of invisible content
- [ ] Link traversal never returns invisible endpoints

### 5.4 Logging & Monitoring

- [ ] Access logs sanitized (no object IDs of invisible objects)
- [ ] Error logs generic (no "object not found" vs "access denied" distinction)
- [ ] Metrics do not count invisible objects
- [ ] Audit logs only accessible to account owner

---

## 6. Testing Strategy

### 6.1 Unit Tests

- [ ] `isVisible()` function correctly evaluates each object type
- [ ] Ownership rules enforced (owner always visible)
- [ ] Public objects visible to all authenticated users
- [ ] Shared objects visible only to library members
- [ ] Deleted objects not visible
- [ ] Parent object visibility required for child objects

### 6.2 Integration Tests

- [ ] User A cannot see User B's documents
- [ ] User A can see documents in shared library
- [ ] User A cannot see highlights on invisible documents
- [ ] Retrieval filters out invisible chunks
- [ ] LLM context only includes visible sources
- [ ] 404 returned for invisible objects (no 403)

### 6.3 Security Tests

- [ ] Timing attacks do not leak object existence
- [ ] Error messages do not reveal object existence
- [ ] Batch operations do not leak counts
- [ ] Link traversal does not return invisible endpoints
- [ ] Vector embeddings of invisible content not exposed

