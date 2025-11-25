# Permissions & Ownership Model

## 1. Overview

The permissions model is based on **ownership** and **visibility**:

- **Ownership**: Users own the documents they upload, highlights they create, conversations they start
- **Visibility**: Controlled via libraries, subscriptions, and explicit sharing
- **ACL**: All access control derived from `Visible(U, O)` function (see [spec/acl.md](acl.md))

---

## 2. Libraries

Libraries are the primary sharing mechanism for documents and collaborative collections.

### 2.1 Library Structure

```sql
CREATE TABLE libraries (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  is_public BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_libraries_user ON libraries(user_id);
```

**Fields**:

- `id`: Library UUID
- `user_id`: Owner (creator) of the library
- `name`: Display name (e.g., "Research - ML")
- `description`: Optional notes on library purpose
- `is_public`: If true, library is discoverable (Phase 2+)
- `created_at`, `updated_at`: Timestamps

### 2.2 Library Memberships

```sql
CREATE TABLE library_memberships (
  id UUID PRIMARY KEY,
  library_id UUID NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer'))
    DEFAULT 'viewer',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (library_id, user_id)
);

CREATE INDEX idx_library_memberships_user ON library_memberships(user_id);
```

**Roles**:

- `owner`: Full control (share, delete, invite, leave)
- `editor`: Add/remove documents, create highlights
- `viewer`: Read-only access to library contents

### 2.3 Media in Libraries

```sql
CREATE TABLE library_media (
  id UUID PRIMARY KEY,
  library_id UUID NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
  media_type TEXT NOT NULL CHECK (media_type IN ('document', 'episode', 'video')),
  media_id UUID NOT NULL,
  added_by_user_id UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (library_id, media_type, media_id)
);

CREATE INDEX idx_library_media_library ON library_media(library_id);
CREATE INDEX idx_library_media_media ON library_media(media_type, media_id);
```

**Invariant**: Each document can be in multiple libraries.

---

## 3. Subscriptions (Episodes/Videos, Phase 2+)

For podcasts and video channels:

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

Episodes of subscribed podcasts are visible to the subscriber.

---

## 4. Object Visibility Overlays

For fine-grained sharing of individual objects (highlights, annotations, conversations, messages):

```sql
CREATE TABLE object_library_visibility (
  id UUID PRIMARY KEY,
  object_type TEXT NOT NULL CHECK (object_type IN ('highlight', 'annotation', 'conversation', 'message')),
  object_id UUID NOT NULL,
  library_id UUID NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
  shared_by_user_id UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE (object_type, object_id, library_id)
);

CREATE INDEX idx_object_visibility_library ON object_library_visibility(library_id);
CREATE INDEX idx_object_visibility_object ON object_library_visibility(object_type, object_id);
```

**Semantics**: An object is visible to a user if:

1. User is the owner, OR
2. Object is public (`is_public = true`), OR
3. Object is shared to a library the user is member of

---

## 5. Public Objects

Some objects can be marked `is_public = true`:

- **Highlights**: User explicitly shares their highlight
- **Annotations**: User shares their note
- **Conversations**: User shares their entire conversation
- **Messages**: User shares individual messages (subject to conversation visibility)

**Visibility rule**: `is_public=true` means the object is visible to any authenticated user, but may still be restricted if the underlying source (media) is not visible.

Example: A highlight on a private document can be public in terms of the highlight's visibility setting, but is only visible to users who can see the document (library members).

---

## 6. Ownership

### 6.1 Documents

- **Created by**: User who uploaded the document
- **Modifiable by**: Owner only (delete, update metadata)
- **Visible to**: Library members (if in library) or owner if private

### 6.2 Highlights

- **Created by**: User who created the highlight
- **Modifiable by**: Owner only (color, visibility, hidden flag)
- **Visible to**: Depends on `Visible(U, highlight)` (see [spec/acl.md](acl.md))

### 6.3 Annotations

- **Created by**: User who wrote the note
- **Modifiable by**: Owner only
- **Visible to**: Depends on highlight visibility + annotation visibility

### 6.4 Conversations

- **Created by**: User who initiated the conversation
- **Modifiable by**: Owner only (delete, sharing)
- **Visible to**: Owner or if shared to library or public

### 6.5 Links

- **Created by**: User who created the link
- **Modifiable by**: Owner only (delete)
- **Visible to**: Only traversed from visible objects (not independently visible)

---

## 7. Soft Deletion & Retention

### 7.1 Soft Deletes

All user-created objects support soft deletion:

```sql
ALTER TABLE documents ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE highlights ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE annotations ADD COLUMN deleted_at TIMESTAMPTZ;
ALTER TABLE conversations ADD COLUMN deleted_at TIMESTAMPTZ;
```

**Deleted objects**:

- Not returned in list endpoints
- May return 404 on get endpoints (as if non-existent)
- Preserved in database for 30 days
- Permanently purged after 30 days (background cleanup job)

### 7.2 Cascade Deletion

When deleting a document:

1. Mark document `deleted_at = NOW()`
2. Cancel any in-progress jobs
3. Do NOT delete highlights (preserve for audit)
4. Mark highlights with same `deleted_at` value (optional, for grouping)
5. After 30 days: delete document and all associated highlights, chunks, embeddings

---

## 8. Rate Limiting & Quotas

### 8.1 Phase 1

No quotas or rate limiting in Phase 1. System assumes trusted users with reasonable behavior.

### 8.2 Phase 2+ Quotas

To be designed in Phase 2:

- Max documents per user: 10,000
- Max library memberships: 100
- Max highlights per document: 10,000
- Max conversation length: 500 messages

Rate limiting:

- API request rate: 100 req/sec per user
- Embedding API: Batched to minimize cost

---

## 9. Data Isolation

### 9.1 User Isolation

No explicit data isolation in Phase 1 (single database, single Postgres instance). ACL enforced at application layer.

Risk: Database breach exposes all data. Mitigated via:
- Encrypted Postgres at rest
- TLS for connections
- Automated backups with encryption
- 30-day backup retention

### 9.2 Cross-Tenant Safety

The system is single-tenant (one organization) or multi-tenant with weak isolation. Assumptions:

- All users are trusted (no adversarial users)
- Database access is not compromised
- Network is secure (TLS)

**Not a defense against**:
- Insider threats (disgruntled employee with DB access)
- Supply chain attacks (compromised dependencies)

---

## 10. Privacy Considerations

### 10.1 Personal Data

The system collects and stores:

- User email (from Clerk)
- Document content (uploaded by user)
- Highlight/annotation text (created by user)
- Conversation history (created by user)

All data is stored in Postgres, encrypted at rest via database encryption.

### 10.2 Data Retention

- **Active data**: Stored indefinitely
- **Deleted data**: 30-day retention before permanent deletion
- **Audit logs**: 30-day retention (Phase 2+)
- **Job logs**: 7-day retention

### 10.3 Export & Portability

Users can export their data (Phase 2+):

- Documents: PDF export
- Highlights: JSON export with offsets
- Conversations: Text or PDF export
- All data: SQL dump (for advanced users)

---

## 11. Invitation & Sharing Flow

### 11.1 Inviting Users to Library

1. Owner invites user via email
2. System creates invitation record (not yet a member)
3. Invited user accepts (via link or UI)
4. System creates membership with role specified

### 11.2 Sharing Objects

1. Owner marks object `is_public = true`, OR
2. Owner adds object to shared library via `object_library_visibility`

### 11.3 Leaving/Removing

- User can leave library (membership deleted)
- Owner can remove user from library
- Objects shared by removed user remain visible if also shared to library (shared independently)

---

## 12. Summary Table

| Entity | Owner | Share Mechanism | Visibility Function |
|--------|-------|-----------------|-------------------|
| Document | Uploader | Libraries | Library membership |
| Episode | - | Subscriptions | Podcast subscription (Phase 2) |
| Video | - | Libraries | Library membership |
| Highlight | Creator | Public flag, libraries | Owner OR public OR shared library |
| Annotation | Creator | Public flag, libraries | Highlight visibility |
| Conversation | Creator | Public flag, libraries | Owner OR public OR shared library |
| Message | Creator | Public flag | Conversation visibility |
| Link | Creator | (not shareable) | Both endpoints visible |

