# Schema: Links (NEW in v1)

## Overview

**Links** are first-class entities representing symmetric, untyped relationships between objects in the system. v1 supports basic "related" links; typed links (e.g., "cites", "contradicts") are deferred to Phase 2.

---

## 1. Links Table

```sql
CREATE TABLE links (
  id UUID PRIMARY KEY,

  -- Source object (first endpoint)
  source_type TEXT NOT NULL,
  source_id UUID NOT NULL,

  -- Target object (second endpoint)
  target_type TEXT NOT NULL,
  target_id UUID NOT NULL,

  -- Creator
  created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Uniqueness constraint (canonical ordering)
  UNIQUE (source_type, source_id, target_type, target_id),

  CONSTRAINT no_self_links CHECK (
    NOT (source_type = target_type AND source_id = target_id)
  ),

  CONSTRAINT valid_source_type CHECK (
    source_type IN ('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')
  ),

  CONSTRAINT valid_target_type CHECK (
    target_type IN ('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')
  )
);

CREATE INDEX idx_links_source ON links(source_type, source_id);
CREATE INDEX idx_links_target ON links(target_type, target_id);
CREATE INDEX idx_links_creator ON links(created_by_user_id);
```

---

## 2. Link Invariants

### 2.1 Symmetry

Links are **logically symmetric**:

- Link `(A, B)` is equivalent to link `(B, A)`
- Only one row stored in canonical ordering
- Canonical ordering: Sort by `(source_type, source_id, target_type, target_id)` lexicographically

**Example**: Creating link from document D to highlight H:

```python
def create_link(source_type, source_id, target_type, target_id, user_id):
    # Canonical ordering: ensure source comes before target
    if (source_type, source_id) > (target_type, target_id):
        source_type, source_id, target_type, target_id = \
            target_type, target_id, source_type, source_id

    # Insert
    db.execute("""
        INSERT INTO links (source_type, source_id, target_type, target_id, created_by_user_id)
        VALUES (?, ?, ?, ?, ?)
    """, [source_type, source_id, target_type, target_id, user_id])
```

### 2.2 No Self-Links

v1 disallows links from an object to itself (constraint enforced in schema):

```sql
CONSTRAINT no_self_links CHECK (
  NOT (source_type = target_type AND source_id = target_id)
)
```

### 2.3 Deduplication

The UNIQUE constraint on `(source_type, source_id, target_type, target_id)` prevents duplicate links:

```sql
UNIQUE (source_type, source_id, target_type, target_id)
```

Creating the same link twice (in either direction) will fail with a unique constraint violation.

---

## 3. Visibility Semantics

**Critical**: Links themselves are NOT independently visible resources.

### 3.1 Retrieval Rules

When resolving links for object `O` as user `U`:

1. Find all links where `source = O` or `target = O`
2. For each link, check if both endpoints are visible to `U`:
   ```python
   if Visible(U, source) and Visible(U, target):
       include_link()
   ```
3. Never return link metadata for invisible endpoints

### 3.2 Link Traversal

```typescript
async function getLinkedObjects(userId, objectId) {
  // Find all links involving this object
  const links = await db.query(`
    SELECT * FROM links
    WHERE (source_type = ?, source_id = ?)
       OR (target_type = ?, target_id = ?)
  `, [objectType, objectId, objectType, objectId]);

  // Filter by visibility of both endpoints
  const visibleLinks = [];
  for (const link of links) {
    const sourceObj = await loadObject(link.source_type, link.source_id);
    const targetObj = await loadObject(link.target_type, link.target_id);

    if (Visible(userId, sourceObj) && Visible(userId, targetObj)) {
      // Determine which endpoint is the "other" one
      const otherType = (link.source_type === objectType && link.source_id === objectId)
        ? link.target_type
        : link.source_type;
      const otherId = (link.source_type === objectType && link.source_id === objectId)
        ? link.target_id
        : link.source_id;

      visibleLinks.push({
        linkId: link.id,
        otherType: otherType,
        otherObject: otherType === link.target_type ? targetObj : sourceObj
      });
    }
    // If both endpoints not visible: silently skip (do NOT leak existence)
  }

  return visibleLinks;
}
```

### 3.3 ACL Enforcement

Links do NOT grant additional visibility:

- A user cannot see object B just because B is linked to A
- Both A and B must already be visible to the user
- Links are used ONLY for discovery/recommendations, not for access

---

## 4. Supported Link Types (v1)

v1 supports only one link relationship: **"related"** (implicit, no type field).

All links represent general semantic relationships:

- Document → Document (e.g., "related paper")
- Document → Highlight (e.g., "related key insight")
- Highlight → Highlight (e.g., "contradictory highlights")
- Message → Document (e.g., "discussed in conversation")
- Conversation → Conversation (e.g., "continuation")
- Any → Any (symmetric, undirected)

**Future (Phase 2+)**: Add `link_type` field for typed relationships:

```sql
link_type TEXT NOT NULL DEFAULT 'related'
  CHECK (link_type IN ('related', 'cites', 'contradicts', 'expands', ...))
```

---

## 5. Usage Patterns

### 5.1 Optional UI Features

Links enable optional "see related items" panels:

```typescript
// In document viewer
const relatedItems = await getLinkedObjects(userId, documentId);
if (relatedItems.length > 0) {
  renderRelatedPanel(relatedItems);
}
```

### 5.2 Retrieval Boost (Optional)

Retrieval may optionally boost relevance for linked objects:

```python
def retrieve_with_link_boost(query, user_id):
    # Get base results
    results = vector_search(query, k * 3)

    # Optional: for each result, check if linked to user's recent objects
    # and apply boost factor (not implemented in v1, deferred to Phase 2)

    return results
```

This is optional and not required for v1.

### 5.3 Serialization in API

Links returned when navigating related objects:

```json
{
  "id": "doc_550e8400-...",
  "title": "Document Title",
  "related": [
    {
      "link_id": "link_550e8406-...",
      "type": "highlight",
      "id": "hl_550e8402-...",
      "text": "Related highlight text"
    },
    {
      "link_id": "link_550e8407-...",
      "type": "document",
      "id": "doc_550e8408-...",
      "title": "Related document"
    }
  ]
}
```

---

## 6. Implementation Notes

### 6.1 Deletion

When deleting an object, cascade delete associated links:

```sql
ON DELETE CASCADE
```

All links referencing the deleted object are automatically removed.

### 6.2 Bulk Operations

Creating multiple links (e.g., on import):

```python
def create_bulk_links(links, user_id):
    """Idempotent bulk link creation."""
    for link in links:
        try:
            create_link(
                link['source_type'], link['source_id'],
                link['target_type'], link['target_id'],
                user_id
            )
        except IntegrityError:
            # Link already exists, skip
            pass
```

### 6.3 Query Performance

Indexes on `(source_type, source_id)` and `(target_type, target_id)` enable efficient lookups:

```sql
CREATE INDEX idx_links_source ON links(source_type, source_id);
CREATE INDEX idx_links_target ON links(target_type, target_id);
```

Typical queries return < 100 links per object (acceptable performance).

---

## 7. Future Extensions (Phase 2+)

- **Typed links**: Add `link_type` field, allow filtering by type
- **Weighted links**: Add `weight` or `confidence` field for ranker boost
- **Temporal links**: Track when links become stale (e.g., when linked document is deleted)
- **Bidirectional naming**: "cites" vs "cited_by" for directed links
- **Link metadata**: Add custom attributes (e.g., `{"reason": "shares methodology"}`)

