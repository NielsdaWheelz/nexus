# Nexus Subsystem Spec: Libraries, Permissions & Visibility

## 1. Scope

This subsystem handles all library management, membership/role management, media-library associations, and visibility rules for social objects (highlights, annotations, messages, conversations) in Nexus. It is responsible for defining and enforcing the authorization model that controls what users can see and do throughout the system.

**In scope:**
- Library lifecycle: creation, renaming, deletion (with constraints)
- Default library creation and enforcement of default library invariants
- LibraryUser management: membership, roles (owner/admin vs member); promotions/demotions are out of scope in v1
- LibraryMedia management: adding/removing media to/from libraries
- Default library coupling: auto-add to default; removing from default cascades to owner's personal libraries
- Library state transitions: unshared ↔ shared
- Visibility rule specification: the authoritative definition of who can see which social objects
- Permission checks: who can perform library operations (rename, add/remove media, manage members)
- HTTP endpoints for all library operations
- Observability for library operations

**Explicitly out of scope (non-goals):**
- Media ingestion, processing, chunking, embeddings (owned by ingestion subsystem)
- Search implementation (search subsystem must obey visibility rules defined here)
- Highlight/annotation/conversation creation and storage (owned by respective subsystems)
- Billing/subscription logic (but this subsystem calls quota checks where needed)
- UI details beyond what's needed to explain API behavior
- Invitation flows, email notifications, user discovery (future subsystems)
- Library discovery, public libraries, library search (v1: libraries invisible to non-members)

## 2. Dependencies

### Inconsistencies with Existing Docs

The updated invariants provided in this spec resolve the following conflicts with domain-model.md and prd.md:

1. **Owner membership requirement (RESOLVED CONFLICT):**
   - **Domain model stated:** "Owner MUST always be a member of that library with role='admin'. An owner who is not a member is not allowed."
   - **Updated invariant (this spec):** Owner **must** always be a member and an admin; owner cannot leave or demote themselves. Permissions are derived from LibraryUser rows, and owner_user_id exists only alongside membership.
   - **Rationale:** Keeps a single accountable admin per library in v1 and avoids zero-admin libraries.

2. **Default library renaming (UPDATED):**
   - **Domain model stated:** "Default libraries cannot be renamed (v1 product constraint)."
   - **PRD stated:** Same.
   - **Updated invariant (this spec):** Default libraries may be renamed in v1 (name constraints still apply). This supersedes earlier prohibitions.

3. **Removing media from default library (UPDATED):**
   - **Domain model stated:** "Removing media from default library removes it from all unshared libraries owned by that user (member_count == 1)."
   - **Updated invariant (this spec):** Cascade is enforced: removing from default also removes from the owner's personal (sole-member) libraries.

**This spec proceeds with the updated invariants listed above. All conflicts are resolved in favor of the updated rules.**

### External Services

- PostgreSQL database (Library, LibraryUser, LibraryMedia, Media tables)
- Authentication subsystem (for current_user_id extraction from session/JWT)

### Internal Subsystems

- **Ingestion subsystem:** This subsystem creates LibraryMedia rows (default library auto-add). Ingestion owns Media creation; this subsystem owns LibraryMedia lifecycle.
- **Quota/billing subsystem:** For tier limit checks (if library creation or membership limits are ever enforced; v1: no limits).
- **Social object subsystems (highlights, annotations, conversations):** These subsystems depend on this spec for their visibility checks. They MUST call visibility rule functions defined here; they MUST NOT implement their own bespoke visibility logic.

### Database Schema Dependencies and Write Permissions

| Table | Who Can Write | Notes |
|-------|---------------|-------|
| `library` | This subsystem only | Full lifecycle ownership: create, rename, delete |
| `library_user` | This subsystem only | Full lifecycle ownership: add/remove members and manage roles |
| `library_media` | This subsystem + Ingestion subsystem | Ingestion: inserts default library rows. This subsystem: full lifecycle (add/remove media from any library). Both share write access. |
| `media` | Ingestion subsystem only | This subsystem never writes to media table |

**Critical constraints:**
- Ingestion MUST insert (default_library, media_id) rows when media is created
- This subsystem MUST enforce all default library invariants (never shared, never deleted, exactly one member)
- This subsystem owns all LibraryMedia writes except default library initial insertion

## 3. Responsibilities

This subsystem MUST:

1. **Default library lifecycle:**
   - Create default library on user registration (library.is_default = true, library.owner_user_id = user.id)
   - Create LibraryUser row for default library (user, role='admin')
   - Ensure default library is never deleted
   - Ensure default library never has more than one LibraryUser row
   - Reject all attempts to add members to default library
   - Reject all attempts to delete default library

2. **Non-default library lifecycle:**
   - Create libraries with (name, owner_user_id, is_default=false)
   - Rename libraries (admin-only; default and non-default allowed)
   - Delete libraries (only if admin, only if not default, with member/media cleanup)
   - Track ownership via owner_user_id (immutable field); owner remains a member/admin for the life of the library

3. **Membership management (LibraryUser):**
   - Add members to libraries (default role = `member`; admins may promote/demote members to/from `admin`)
   - Remove members from libraries (but never the owner)
   - Role changes are in scope: admin-only promotion/demotion; owner remains admin and cannot be demoted
   - Enforce constraints: default library has exactly one LibraryUser row (the owner); non-default libraries must always retain at least one admin (owner counts) and have ≥1 member
   - Enforce constraint: (library_id, user_id) unique

4. **Media-library associations (LibraryMedia):**
   - Add media to libraries (admin-only operation)
   - Remove media from libraries (admin-only operation)
   - Enforce default library coupling:
     - When (user U, library L, media M) relation is created, ensure (U.default_library, M) exists
     - When a user joins library L, add all existing media in L to their default library
     - When M is removed from U's default library D, also remove M from libraries where U is the sole member (personal libraries only)
   - Enforce constraint: (library_id, media_id) unique
   - Coupling writes must be atomic (single transaction, all-or-nothing) with retry on serialization failure.

5. **Visibility rule enforcement (authoritative specification):**
   - Define the formal visibility rule for social objects
   - Provide read APIs or internal functions that other subsystems can call to check visibility
   - Ensure search, highlight, annotation, conversation subsystems use these rules

6. **Read APIs:**
   - List user's libraries (default + non-default)
   - List media in a given library (paginated)
   - Get library details (only if member)
   - List members of a library (only if member)

7. **Observability:**
   - Emit structured logs for all library operations
   - Track metrics: library creation/deletion, membership changes, media add/remove (default auto-add optional)

This subsystem MUST NOT:

1. Create Media rows (ingestion subsystem responsibility)
2. Process, chunk, or embed media (ingestion subsystem responsibility)
3. Implement search queries (search subsystem responsibility)
4. Store or manage highlights, annotations, conversations (respective subsystems)
5. Implement billing logic (calls quota checks only)
6. Send invitation emails or user notifications (future subsystems)
7. Allow any operation that violates default library invariants

## 4. External Interfaces

### 4.1 HTTP Endpoints

All endpoints require authentication. `current_user_id` is extracted from session/JWT.

---

#### POST /api/v1/libraries

**Purpose:** Create a new library (non-default).

**Request:**
```json
{
  "name": "Book Club Reading List"
}
```

**Fields:**
- `name` (required, string, max 200 chars): Library name.

**Response (201 Created):**
```json
{
  "id": "uuid",
  "name": "Book Club Reading List",
  "owner_user_id": "uuid",
  "is_default": false,
  "member_count": 1,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

**Error Codes:**
- `400 INVALID_NAME`: Name is empty or exceeds max length.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Validate `name` (non-empty, max 200 chars).
2. Within transaction:
   a. Insert `Library` row: `name`, `owner_user_id=current_user_id`, `is_default=false`.
   b. Insert `LibraryUser` row: `library_id`, `user_id=current_user_id`, `role='admin'`.
   c. Commit transaction.
4. Return `201` with library object.

**Concurrency:**
- No constraints on concurrent library creation by same user
- Multiple libraries with same name are allowed (no uniqueness constraint on name)

---

#### GET /api/v1/libraries

**Purpose:** List all libraries the current user is a member of.

**Query Parameters:**
- `limit` (optional, int, default=50, max=100): Number of results per page.
- `offset` (optional, int, default=0): Pagination offset.

**Response (200 OK):**
```json
{
  "libraries": [
    {
      "id": "uuid",
      "name": "My Library",
      "owner_user_id": "uuid",
      "is_default": true,
      "member_count": 1,
      "role": "admin",
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-01T00:00:00Z"
    },
    {
      "id": "uuid",
      "name": "Book Club Reading List",
      "owner_user_id": "uuid",
      "is_default": false,
      "member_count": 3,
      "role": "member",
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

**Behavior:**
1. Query `LibraryUser` table by `user_id=current_user_id`.
2. Join with `Library` table to retrieve library details.
3. For each library, compute `member_count` (count of LibraryUser rows for that library).
4. Order by: `is_default DESC, created_at DESC, id DESC` (default library first, then most recent).
5. Apply pagination (limit, offset).
6. Return libraries with current user's role.

**Note:**
- Default library always appears first (is_default DESC).
- `role` field indicates current user's role in that library.
- Libraries are invisible to non-members (not included in results).

---

#### GET /api/v1/libraries/{id}

**Purpose:** Retrieve library details (only if member).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "Book Club Reading List",
  "owner_user_id": "uuid",
  "is_default": false,
  "member_count": 3,
  "role": "admin",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-20T14:00:00Z"
}
```

**Error Codes:**
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member (indistinguishable for security).
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. Query `Library` table by `id`.
4. Compute `member_count`.
5. Return library object with current user's role.

**Security:**
- Libraries are invisible to non-members.
- 404 for both "does not exist" and "not a member" prevents enumeration.

---

#### PATCH /api/v1/libraries/{id}

**Purpose:** Rename a library (admin-only, default and non-default).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Request:**
```json
{
  "name": "Updated Book Club Name"
}
```

**Fields:**
- `name` (required, string, max 200 chars): New library name.

**Response (200 OK):**
```json
{
  "id": "uuid",
  "name": "Updated Book Club Name",
  "owner_user_id": "uuid",
  "is_default": false,
  "member_count": 3,
  "role": "admin",
  "updated_at": "2025-01-20T14:00:00Z"
}
```

**Error Codes:**
- `400 INVALID_NAME`: Name is empty or exceeds max length.
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Validate `name` (non-empty, max 200 chars).
2. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
3. If no row found: return `404 LIBRARY_NOT_FOUND`.
4. If `role != 'admin'`: return `403 INSUFFICIENT_PERMISSIONS`.
5. Update `Library` set `name`, `updated_at=now()`.
6. Return `200` with updated library object.

---

#### DELETE /api/v1/libraries/{id}

**Purpose:** Delete a library (admin-only, non-default only).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Response (204 No Content):**
```
(empty body)
```

**Error Codes:**
- `400 CANNOT_DELETE_DEFAULT_LIBRARY`: Attempting to delete default library (forbidden).
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. If `role != 'admin'`: return `403 INSUFFICIENT_PERMISSIONS`.
4. Query `Library` by `id`.
5. If `is_default = true`: return `400 CANNOT_DELETE_DEFAULT_LIBRARY`.
6. Within transaction:
   a. Delete all `LibraryUser` rows for `library_id` (cascade delete all members).
   b. Delete all `LibraryMedia` rows for `library_id` (remove all media associations).
   c. Delete `Library` row.
   d. Commit transaction.
7. Return `204`.
8. Emit log: `{"event": "library_deleted", "library_id": "...", "deleted_by_user_id": "...", "member_count": N, "media_count": M}`.

**Consequences:**
- All members lose access to library (visibility may change).
- Media remains in system (global, not deleted).
- Social objects attached to media remain (visibility may change based on other libraries).
- This operation is not reversible.

---

#### GET /api/v1/libraries/{id}/members

**Purpose:** List members of a library (member-only access).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Query Parameters:**
- `limit` (optional, int, default=50, max=100): Number of results per page.
- `offset` (optional, int, default=0): Pagination offset.

**Response (200 OK):**
```json
{
  "members": [
    {
      "user_id": "uuid",
      "email": "user@example.com",
      "display_name": "Alice",
      "role": "admin",
      "joined_at": "2025-01-15T10:30:00Z"
    },
    {
      "user_id": "uuid",
      "email": "user2@example.com",
      "display_name": "Bob",
      "role": "member",
      "joined_at": "2025-01-16T12:00:00Z"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

**Error Codes:**
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. Query all `LibraryUser` rows by `library_id`, join with `User` table to retrieve user details.
4. Order by: `role DESC, joined_at ASC` (admins first, then by join time).
5. Apply pagination.
6. Return members list.

**Note:**
- All members can view member list (not admin-only).
- `joined_at` is derived from LibraryUser row creation timestamp (if column exists) or `created_at` (if not).

---

#### POST /api/v1/libraries/{id}/members

**Purpose:** Add a member to a library (admin-only).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Request:**
```json
{
  "user_id": "uuid",
  "role": "member"
}
```

**Fields:**
- `user_id` (required, UUID): User ID to add.
- `role` (optional, enum `member`|`admin`; default `member`. Only admins may set `admin`.)

**Response (201 Created):**
```json
{
  "user_id": "uuid",
  "email": "user@example.com",
  "display_name": "Alice",
  "role": "member",
  "joined_at": "2025-01-20T15:00:00Z"
}
```

**Error Codes:**
- `400 CANNOT_ADD_MEMBER_TO_DEFAULT_LIBRARY`: Attempting to add member to default library (forbidden).
- `400 USER_ALREADY_MEMBER`: User is already a member of this library.
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `404 USER_NOT_FOUND`: Target user_id does not exist.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. If current user's `role != 'admin'`: return `403 INSUFFICIENT_PERMISSIONS`.
4. Query `Library` by `id`.
5. If `is_default = true`: return `400 CANNOT_ADD_MEMBER_TO_DEFAULT_LIBRARY`.
6. Query `User` by `user_id` to verify existence. If not found: return `404 USER_NOT_FOUND`.
7. Attempt to insert `LibraryUser` row: `library_id`, `user_id`, `role` (default `member`). If requested role=`admin`, caller must be admin; owner remains admin regardless.
8. If unique constraint violation (user already member): return `400 USER_ALREADY_MEMBER`.
9. **Trigger default library coupling:**
   - Query all media in library L: `SELECT media_id FROM library_media WHERE library_id = L`.
   - For each media M:
     - Get new member's default library D: `SELECT id FROM library WHERE owner_user_id = user_id AND is_default = true`.
     - Insert `LibraryMedia(library_id=D, media_id=M)` with `ON CONFLICT DO NOTHING` (idempotent).
10. Return `201` with member object.
11. Emit log: `{"event": "member_added", "library_id": "...", "user_id": "...", "role": "member", "added_by_user_id": "..."}`.

**Consequences:**
- New member can now see all media in library.
- All media in library are added to new member's default library.
- New member can see social objects (highlights, annotations, messages) on shared media from other members.

---

#### DELETE /api/v1/libraries/{id}/members/{user_id}

**Purpose:** Remove a member from a library (admin can remove others; any member can remove self).

**Path Parameters:**
- `id` (required, UUID): Library ID.
- `user_id` (required, UUID): User ID to remove.

**Response (204 No Content):**
```
(empty body)
```

**Error Codes:**
- `400 CANNOT_REMOVE_FROM_DEFAULT_LIBRARY`: Attempting to remove member from default library (forbidden; default library has exactly one member).
- `400 CANNOT_REMOVE_OWNER`: Attempting to remove the owner (forbidden).
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin and is trying to remove someone else.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `404 MEMBER_NOT_FOUND`: Target user_id is not a member of this library.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. Query `Library` by `id`.
4. If `is_default = true`: return `400 CANNOT_REMOVE_FROM_DEFAULT_LIBRARY`.
5. If `user_id` is the owner_user_id: return `400 CANNOT_REMOVE_OWNER` (owner cannot leave).
6. If `user_id != current_user_id` (removing someone else) AND current user's `role != 'admin'`: return `403 INSUFFICIENT_PERMISSIONS`.
7. Query `LibraryUser` by `library_id` and `user_id` (target user).
8. If no row found: return `404 MEMBER_NOT_FOUND`.
9. **Enforce at least one admin:** If target user is the last admin (including owner), reject removal.
10. Within transaction:
    a. Delete `LibraryUser` row for `library_id` and `user_id`.
    b. Commit transaction.
11. Return `204`.
12. Emit log: `{"event": "member_removed", "library_id": "...", "user_id": "...", "removed_by_user_id": "..."}`.

**Consequences:**
- Removed member loses access to library (visibility may change).
- Removed member's highlights/annotations on media in this library become invisible to remaining members (unless shared via another library).
- Library must still have the owner/admin after removal; never remove or demote owner.
- Media already in the removed member's default library remains there (global media is still readable); only social visibility is lost.

---

#### PATCH /api/v1/libraries/{id}/members/{user_id}

**Purpose:** Change a member's role (admin-only; cannot demote owner; must preserve at least one admin).

**Request:**
```json
{
  "role": "admin"
}
```

**Fields:**
- `role` (required, enum `member`|`admin`)

**Error Codes:**
- `400 INVALID_ROLE`: Role is not `member` or `admin`.
- `400 CANNOT_MODIFY_DEFAULT_LIBRARY`: Attempting to change membership of default library (default remains single-member).
- `400 CANNOT_DEMOTE_OWNER`: Attempting to change owner role (owner stays admin).
- `400 MUST_RETAIN_ADMIN`: Operation would leave library with zero admins.
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `404 MEMBER_NOT_FOUND`: Target user_id is not a member of this library.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Validate `role`.
2. Query `LibraryUser` for current user; if missing → `404 LIBRARY_NOT_FOUND`.
3. If caller role != admin → `403 INSUFFICIENT_PERMISSIONS`.
4. Query `Library`; if default → `400 CANNOT_MODIFY_DEFAULT_LIBRARY`.
5. Query target membership; if missing → `404 MEMBER_NOT_FOUND`.
6. If target is owner → `400 CANNOT_DEMOTE_OWNER`.
7. If setting role=`member`, ensure at least one other admin remains (including owner) else `400 MUST_RETAIN_ADMIN`.
8. Update role; return `200` with updated member payload.
9. Emit log: `{"event": "member_role_changed", "library_id": "...", "user_id": "...", "role": "...", "changed_by_user_id": "..."}`.

**Consequences:**
- Multiple admins supported; promotions/demotions are explicit and admin-gated.

---

#### GET /api/v1/libraries/{id}/media

**Purpose:** List media in a library (member-only access).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Query Parameters:**
- `limit` (optional, int, default=50, max=100): Number of results per page.
- `offset` (optional, int, default=0): Pagination offset.

**Response (200 OK):**
```json
{
  "media": [
    {
      "id": "uuid",
      "kind": "html",
      "title": "Article Title",
      "authors": [{"id": "uuid", "name": "Author Name"}],
      "canonical_url": "https://example.com/article",
      "processing_status": "indexed",
      "added_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

**Error Codes:**
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. Query `LibraryMedia` by `library_id`, join with `Media` table.
4. Join with `MediaAuthor` and `Author` tables to retrieve authors.
5. Order by: `added_at DESC, media.id DESC`.
6. Apply pagination.
7. Return media list.

**Note:**
- All members can view library media (not admin-only).
- Media is globally readable (any user can read any media), but this endpoint filters by library membership.

---

#### POST /api/v1/libraries/{id}/media

**Purpose:** Add media to a library (admin-only).

**Path Parameters:**
- `id` (required, UUID): Library ID.

**Request:**
```json
{
  "media_id": "uuid"
}
```

**Fields:**
- `media_id` (required, UUID): Media ID to add.

**Response (201 Created):**
```json
{
  "id": "uuid",
  "kind": "html",
  "title": "Article Title",
  "authors": [{"id": "uuid", "name": "Author Name"}],
  "canonical_url": "https://example.com/article",
  "processing_status": "indexed",
  "added_at": "2025-01-20T15:00:00Z"
}
```

**Error Codes:**
- `400 MEDIA_ALREADY_IN_LIBRARY`: Media is already in this library.
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `404 MEDIA_NOT_FOUND`: Media ID does not exist.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. If current user's `role != 'admin'`: return `403 INSUFFICIENT_PERMISSIONS`.
4. Query `Media` by `media_id` to verify existence. If not found: return `404 MEDIA_NOT_FOUND`.
5. Attempt to insert `LibraryMedia` row: `library_id`, `media_id`.
6. If unique constraint violation (media already in library): return `400 MEDIA_ALREADY_IN_LIBRARY`.
7. **Trigger default library coupling:**
   - Query all members of library L: `SELECT user_id FROM library_user WHERE library_id = L`.
   - For each member U:
     - Get U's default library D: `SELECT id FROM library WHERE owner_user_id = U AND is_default = true`.
     - Insert `LibraryMedia(library_id=D, media_id=M)` with `ON CONFLICT DO NOTHING` (idempotent).
8. Return `201` with media object.
9. Emit log: `{"event": "media_added_to_library", "library_id": "...", "media_id": "...", "added_by_user_id": "...", "member_count": N}`.

**Consequences:**
- All members of library can now see media.
- Media is added to all members' default libraries (default library coupling invariant).
- Members can now see each other's social objects (highlights, annotations, messages) on this media (visibility rule).

---

#### DELETE /api/v1/libraries/{id}/media/{media_id}

**Purpose:** Remove media from a library (admin-only).

**Path Parameters:**
- `id` (required, UUID): Library ID.
- `media_id` (required, UUID): Media ID to remove.

**Response (204 No Content):**
```
(empty body)
```

**Error Codes:**
- `403 INSUFFICIENT_PERMISSIONS`: Current user is not admin.
- `404 LIBRARY_NOT_FOUND`: Library ID does not exist OR current user is not a member.
- `404 MEDIA_NOT_IN_LIBRARY`: Media is not in this library.
- `500 INTERNAL_ERROR`: Database error.

**Behavior:**
1. Query `LibraryUser` by `library_id` and `user_id=current_user_id`.
2. If no row found: return `404 LIBRARY_NOT_FOUND`.
3. If current user's `role != 'admin'`: return `403 INSUFFICIENT_PERMISSIONS`.
4. Query `Library` by `id`.
5. Query `LibraryMedia` by `library_id` and `media_id`.
6. If no row found: return `404 MEDIA_NOT_IN_LIBRARY`.
7. **If removing from default library (is_default = true):**
   a. Get owner U of default library: `owner_user_id`.
   b. Query all libraries where U is the sole member (personal libraries, non-default):
      ```sql
      SELECT l.id FROM library l
      JOIN library_user lu ON l.id = lu.library_id
      WHERE l.is_default = false
      GROUP BY l.id
      HAVING COUNT(lu.user_id) = 1 AND MAX(lu.user_id) = U
      ```
   c. Within transaction:
      - Delete `LibraryMedia` row for default library (library_id=D, media_id=M).
      - For each personal library L from step b: delete `LibraryMedia` row (library_id=L, media_id=M).
      - Commit transaction.
   d. Emit log: `{"event": "media_removed_from_default_library", "library_id": "...", "media_id": "...", "removed_by_user_id": "...", "cascade_removed_from_libraries": [L1, L2, ...]}`.
8. **Else (removing from non-default library):**
   a. Delete `LibraryMedia` row.
   b. Emit log: `{"event": "media_removed_from_library", "library_id": "...", "media_id": "...", "removed_by_user_id": "..."}`.
9. Return `204`.

**Consequences:**
- Members lose access to media in this library (but media remains globally readable).
- Visibility may change: members may no longer see each other's social objects on this media (unless shared via another library).
- If removed from default library: it is also removed from all of the owner's personal (sole-member) libraries.

**Note:**
- UI MUST display confirmation dialog when removing from default library, listing affected unshared libraries.

---

### 4.2 Internal Functions / APIs (For Other Subsystems)

Other subsystems (search, highlights, annotations, conversations) MUST call these visibility check functions. They MUST NOT implement their own bespoke visibility logic.

---

#### `can_user_see_social_object(viewer_user_id: UUID, owner_user_id: UUID, media_id: UUID) -> bool`

**Purpose:** Authoritative visibility rule check for social objects.

**Inputs:**
- `viewer_user_id` (UUID): User attempting to view the social object.
- `owner_user_id` (UUID): User who owns the social object (highlight, annotation, message, conversation).
- `media_id` (UUID): Media the social object is attached to.

**Output:**
- `true`: Viewer can see the social object.
- `false`: Viewer cannot see the social object.

**Algorithm:**
1. If `viewer_user_id == owner_user_id`: return `true` (owner can always see own objects).
2. Query: Does there exist a library L such that:
   - `(L, media_id)` exists in LibraryMedia, AND
   - `(L, viewer_user_id)` exists in LibraryUser, AND
   - `(L, owner_user_id)` exists in LibraryUser.
3. If such L exists: return `true` (shared library containing media).
4. Else: return `false` (no shared library ⇒ not visible).

**SQL Implementation (Suggested):**
```sql
SELECT EXISTS (
  SELECT 1
  FROM library_media lm
  JOIN library_user lvu ON lm.library_id = lvu.library_id
  JOIN library_user lvo ON lm.library_id = lvo.library_id
  WHERE lm.media_id   = :media_id
    AND lvu.user_id   = :viewer_user_id
    AND lvo.user_id   = :owner_user_id
)
```

**Complexity:** O(1) with proper indexes on (library_media.media_id, library_user.user_id).

**Critical Constraints:**
- There must be at least one shared library containing M where both viewer and owner are members.
- No transitive visibility: A seeing M with B and B seeing M with C does **not** imply A sees C unless A and C share a library containing M.

---

#### `get_visible_social_object_owners_for_media(viewer_user_id: UUID, media_id: UUID) -> List[UUID]`

**Purpose:** Batch visibility check: return all user IDs whose social objects on media are visible to viewer.

**Inputs:**
- `viewer_user_id` (UUID): User attempting to view social objects.
- `media_id` (UUID): Media to check.

**Output:**
- List of user IDs (including viewer_user_id) whose social objects are visible.

**Algorithm:**
1. Compute viewer libraries containing the media.
2. If viewer has none: return empty list.
3. Return all distinct user_ids from libraries that both:
   - Contain the media, AND
   - Are in the viewer's library set (shared with viewer).
4. Always include `viewer_user_id` in the result (viewer sees own objects).

**SQL Implementation (Suggested):**
```sql
WITH viewer_libs AS (
  SELECT DISTINCT lm.library_id
  FROM library_media lm
  JOIN library_user lu ON lm.library_id = lu.library_id
  WHERE lm.media_id = :media_id AND lu.user_id = :viewer_user_id
),
SELECT DISTINCT lu.user_id
FROM library_user lu
WHERE lu.library_id IN (SELECT library_id FROM viewer_libs)

UNION

SELECT :viewer_user_id
```

**Use Case:**
- Search results: filter highlights/annotations on media to only those visible to viewer.
- Reader UI: load all visible highlights on media for display.

---

#### `get_visible_media_for_user(user_id: UUID, filters: dict) -> List[UUID]`

**Purpose:** Return all media IDs visible to user (optionally filtered by library).

**Inputs:**
- `user_id` (UUID): User to check.
- `filters` (dict, optional): `{"library_id": UUID}` to filter by specific library.

**Output:**
- List of media IDs.

**Algorithm:**
- Media is globally readable in v1.
- If `library_id` filter provided:
  1. Verify user is member: `SELECT 1 FROM library_user WHERE library_id = :library_id AND user_id = :user_id`.
  2. If not member: return empty list.
  3. Query: `SELECT media_id FROM library_media WHERE library_id = :library_id`.
- If no filter provided:
  - Return all media IDs (globally readable): `SELECT id FROM media`.

**Note:**
- In v1, media is globally readable. This function is a placeholder for future per-media visibility flags (v2+).

---

### 4.3 Background Jobs

This subsystem does not require background jobs in v1. All operations are synchronous HTTP requests.

**Future extensions (v2+):**
- Batch visibility recomputation (if visibility rules change retroactively)
- Library cleanup jobs (delete empty libraries, orphaned LibraryMedia rows)

---

## 5. State & Lifecycles

### 5.1 Library Lifecycle

**States:**
- `created`: Library exists, has at least one member.
- `deleted`: Library deleted, all members and media associations removed.

**State Transitions:**
- User creates library → `created` (with creator as admin member).
- Admin deletes library → `deleted` (cascade delete members and media associations).

**No intermediate states:** Libraries are either active or deleted (hard delete in v1).

**Library State Diagram:**
```
┌─────────┐
│ created │  Library exists, has members
└────┬────┘
     │
     │ Admin deletes library (DELETE /libraries/{id})
     ▼
┌─────────┐
│ deleted │  Library row deleted, all members/media removed
└─────────┘
```

**Forbidden Transitions:**
- `deleted` → `created` (no undelete in v1).
- Default library → `deleted` (forbidden by invariants).

---

### 5.2 Library Sharing Transitions (Unshared ↔ Shared)

**Definitions:**
- **Unshared library:** Library with exactly one member (member_count == 1).
- **Shared library:** Library with more than one member (member_count > 1).

**State Diagram:**
```
┌──────────┐                              ┌────────┐
│ unshared │ ──────────────────────────▶ │ shared │
│ (count=1)│  Add member (POST /members) │(count>1)│
└──────────┘                              └────────┘
     ▲                                         │
     │                                         │
     └─────────────────────────────────────────┘
       Remove member, leaving 1 (DELETE /members)
```

**Transition: Unshared → Shared**
- Trigger: Adding member to library where member_count == 1.
- Consequences:
  - Library becomes shared.
  - All media in library are added to new member's default library (default library coupling).
  - New member can see social objects from existing member on shared media.

**Transition: Shared → Unshared**
- Trigger: Removing member from library where member_count == 2 (leaving 1 member).
- Consequences:
  - Library becomes unshared.
  - All media in library are added to remaining member's default library (default library coupling).
  - Removed member's social objects become invisible to remaining member (unless shared via another library).

**Critical Invariant:**
- When library transitions to unshared, all media in library MUST be in remaining member's default library.

---

### 5.3 Membership Lifecycle

**States:**
- `added`: User is a member of library with a role.
- `removed`: User is no longer a member (LibraryUser row deleted).

**State Transitions:**
- Admin adds member → `added`.
- Admin removes member OR member leaves → `removed`.

**Membership State Diagram:**
```
┌───────┐
│ added │  User is member of library with role
└───┬───┘
    │
    │ Admin removes OR member leaves (DELETE /members/{user_id})
    ▼
┌─────────┐
│ removed │  LibraryUser row deleted
└─────────┘
```

**Forbidden Transitions:**
- `removed` → `added` (no "undo" in v1; must re-add as new member).
- Cannot remove sole member from default library (forbidden by invariants).

---

### 5.4 Media-Library Association Lifecycle

**States:**
- `associated`: Media is in library (LibraryMedia row exists).
- `disassociated`: Media is removed from library (LibraryMedia row deleted).

**State Transitions:**
- Admin adds media → `associated`.
- Admin removes media → `disassociated`.

**Media-Library State Diagram:**
```
┌────────────┐
│ associated │  Media is in library
└─────┬──────┘
      │
      │ Admin removes media (DELETE /libraries/{id}/media/{media_id})
      ▼
┌────────────────┐
│ disassociated  │  LibraryMedia row deleted
└────────────────┘
```

**Cascade Removal (Default Library):**
- When media is removed from default library:
  - Also removed from all unshared libraries where user is sole member.
  - This is a multi-library state transition triggered by a single operation.

**Forbidden Transitions:**
- Cannot remove media from non-existent library (404).
- Removing from default library also removes from the owner's personal (sole-member) libraries.

---

## 6. Invariants

### 6.1 Library Invariants

1. **Exactly one default library per user:** Each user MUST have exactly one library where `is_default = true` and `owner_user_id = user.id`. This library is created on user registration and never deleted.

2. **Default library immutability:**
   - Default library CANNOT be deleted by anyone, ever.
   - Default library CANNOT be shared (adding members is forbidden).
   - Default library MUST have exactly one LibraryUser row (the owner with role='admin').
   - Default library name MAY be changed (admin-only rename allowed).

3. **Owner field semantics:**
   - `library.owner_user_id` is immutable metadata in v1; ownership transfer is out of scope.
   - Owner MUST always have a LibraryUser row and MUST be `admin`.
   - Owner cannot leave or be demoted in v1.
   - Permissions are derived from LibraryUser rows; owner_user_id alone conveys no rights.

4. **Library visibility:** Libraries are invisible to non-members. Only members can see library details, media, or other members.

5. **Shared vs unshared definition:**
   - Unshared library: member_count == 1 (exactly one LibraryUser row).
   - Shared library: member_count > 1 (more than one LibraryUser row).
   - Default library is always unshared (member_count == 1 by invariant).

6. **Non-default libraries:**
   - Can be created, renamed, deleted (by admin).
   - Must have at least one member at all times (owner enforces floor).
   - Must always retain at least one admin (owner counts); other members may be promoted to admin by existing admins.

---

### 6.2 Membership Invariants (LibraryUser)

1. **Uniqueness:** `(library_id, user_id)` is unique (enforced by database constraint). A user cannot be a member of the same library twice.

2. **Default library membership:**
   - Default library MUST always have exactly one LibraryUser row (the owner with role='admin').
   - Adding any other LibraryUser rows to default library MUST be rejected (400 error).
   - Removing the sole LibraryUser row from default library MUST be rejected (400 error).

3. **Non-default library membership:**
   - Library MUST always have at least one member.
   - Owner MUST always be a member and remain `admin` (cannot leave, cannot demote).
   - At least one admin MUST exist at all times (owner satisfies floor; other admins allowed).
   - Other members may be promoted/demoted by admins; role changes are in scope.

4. **Role constraints:**
   - Role enum remains `member` or `admin`; multiple admins allowed.
   - Admins can: rename library, add/remove media, invite/remove members, promote/demote roles.
   - Members can: read all media, create own highlights/annotations (creation handled by other subsystems).
   - Owner is always an admin; demoting owner is forbidden.

5. **Permission derivation:**
   - Permissions are derived from LibraryUser rows; owner_user_id alone conveys no rights.
   - If user has no LibraryUser row for library L, they have zero permissions (including owner_user_id-only cases, which are invalid for v1).

---

### 6.3 Media-Library Association Invariants (LibraryMedia)

1. **Uniqueness:** `(library_id, media_id)` is unique (enforced by database constraint). Media cannot be added to same library twice.

2. **Media is global and always readable:** In v1, all authenticated users can read all media (globally readable). Libraries do not hide media; they govern social object visibility and "my collections".

3. **Default library coupling (critical):**
   - **Invariant 3.1:** When `(user U, library L, media M)` relation is created (LibraryMedia row for (L, M) and U is a member of L via LibraryUser), the system MUST ensure: `(U.default_library_id, M)` exists in LibraryMedia. Create it if missing (idempotent).
   - **Invariant 3.2 (member joins library):** When user U is added to library L, all media in L MUST be added to U's default library (idempotent).
   - **Invariant 3.3 (remove from default):** When M is removed from U's default library D, the system MUST also remove M from any library where U is the sole member (personal libraries). Shared libraries are unaffected.
   - **Simplification:** No shared→unshared auto-add in v1; that behavior is deferred.
   - **Summary:** Default library is auto-populated with anything the user encounters; removing from default pulls it from the user's personal libraries only.

4. **LibraryMedia write permissions:**
   - Ingestion subsystem: inserts (default_library, media_id) rows when media is created.
   - This subsystem: full lifecycle (add/remove media from any library, including default).
   - Both subsystems share write access (with above constraints).

---

### 6.4 Visibility Invariants (Social Objects)

**Authoritative Visibility Rule:**

A user V may see a social object (highlight / annotation / message / conversation) owned by user O if and only if:
1. `V == O` (V is the owner), OR
2. There exists some media M such that:
   - The social object is attached (directly or via context) to M, AND
   - There exists at least one library L containing M where **both** V and O are members.

**Formal Set-Theoretic Definition:**

Let:
- `V` = viewer user
- `O` = owner user (creator of social object)
- `S` = social object (highlight, annotation, message, conversation)
- `M` = media that S is attached to
- `libraries(U, M)` = set of libraries where user U is a member AND library contains media M

Then:
```
can_see(V, S) ⟺ (V = O) ∨ ( libraries(V, M) ∩ libraries(O, M) ≠ ∅ )
```

**Consequences:**

1. **Disjoint libraries:** If two users A and B have media M only in disjoint libraries (no shared library containing M):
   - Both can read the document (media is global).
   - They MUST NOT see each other's highlights/annotations/messages on M (no shared library ⇒ empty intersection).

2. **Any shared library:** If there exists any shared library L containing M where A and B are both members:
   - They each see all of the other's social objects on M, regardless of which library they were "created from".
   - Social objects are not library-scoped in schema; they are global, filtered by visibility.

3. **Conversation visibility:** If user B can see one message m from conversation C (because of above rule), B MUST see:
   - The entire conversation C, even if some messages in C reference other media they don't share.
   - There is no per-message privacy within a conversation in v1.
   - Conversations surface only via messages with resolvable context; if no message in C has a visible context for viewer, the conversation is not shown.

4. **Search enforcement:** If user B can see X (highlight / annotation / message / conversation), then:
   - X MUST be included in search results when filters allow it.
   - Search MUST NEVER return X to a user who cannot see it according to the rule above.
   - Visibility checks MUST be enforced via database joins per request (no stale caches or client-side filtering).

5. **Schema constraint:** Do NOT introduce per-library "copy" of highlights / annotations / messages. They stay globally stored and only filtered by visibility. LibraryMedia remains the pivot; we do NOT add library_id to highlight / annotation / message tables.

6. **Product stance:** Public corpus, private social layer. All media is globally readable; only social objects have visibility restrictions.

---

### 6.5 Consistency Invariants

1. **Default library exists on user creation:** When a new user is created, a default library MUST be created with `is_default = true`, `owner_user_id = user.id`, and a LibraryUser row with `role = 'admin'`.

2. **Library deletion cascade:** When a library is deleted, all LibraryUser and LibraryMedia rows for that library MUST be deleted (cascade delete).

3. **Member deletion visibility impact:** When a member is removed from a library, visibility of social objects MAY change immediately (ex-member's highlights become invisible to remaining members, unless shared via another library).

4. **Media removal visibility impact:** When media is removed from a library, visibility of social objects MAY change immediately (members can no longer see each other's social objects on that media, unless shared via another library).

5. **Default library coupling is transitive:** If media M is in library L, and user U is a member of L, then M MUST be in U's default library (enforced via invariant 3.1 and 3.3).

---

## 7. Error Handling

### HTTP Error Codes

| Error Code                           | HTTP Status | Meaning                                               | User Action                          |
|--------------------------------------|-------------|-------------------------------------------------------|--------------------------------------|
| `INVALID_NAME`                       | 400         | Library name is empty or exceeds max length (200 chars) | Provide valid name                   |
| `INVALID_ROLE`                       | 400         | Role is not `member` or `admin`                       | Use valid role                       |
| `CANNOT_DELETE_DEFAULT_LIBRARY`      | 400         | Attempting to delete default library (forbidden)      | Cannot delete default library        |
| `CANNOT_ADD_MEMBER_TO_DEFAULT_LIBRARY` | 400       | Attempting to add member to default library (forbidden) | Cannot share default library       |
| `CANNOT_REMOVE_FROM_DEFAULT_LIBRARY` | 400         | Attempting to remove member from default library (forbidden) | Cannot remove from default library |
| `CANNOT_REMOVE_OWNER`                | 400         | Attempting to remove library owner (forbidden)        | Owner cannot be removed              |
| `CANNOT_MODIFY_DEFAULT_LIBRARY`      | 400         | Attempting to change roles in default library (forbidden) | Default stays single-member          |
| `CANNOT_DEMOTE_OWNER`                | 400         | Attempting to demote owner from admin                 | Owner remains admin                  |
| `MUST_RETAIN_ADMIN`                  | 400         | Operation would leave library with zero admins        | Promote another admin first          |
| `USER_ALREADY_MEMBER`                | 400         | User is already a member of this library              | User is already a member             |
| `MEDIA_ALREADY_IN_LIBRARY`           | 400         | Media is already in this library                      | Media already exists in library      |
| `INSUFFICIENT_PERMISSIONS`           | 403         | Current user is not admin                             | Must be admin to perform operation   |
| `LIBRARY_NOT_FOUND`                  | 404         | Library ID does not exist OR current user is not a member | Library does not exist or no access |
| `USER_NOT_FOUND`                     | 404         | Target user_id does not exist                         | User does not exist                  |
| `MEMBER_NOT_FOUND`                   | 404         | Target user_id is not a member of this library        | User is not a member                 |
| `MEDIA_NOT_FOUND`                    | 404         | Media ID does not exist                               | Media does not exist                 |
| `MEDIA_NOT_IN_LIBRARY`               | 404         | Media is not in this library                          | Media is not in library              |
| `INTERNAL_ERROR`                     | 500         | Unexpected server error                               | Retry or contact support             |

### Security Considerations

1. **Library visibility:** Libraries are invisible to non-members. 404 for both "does not exist" and "not a member" prevents enumeration.

2. **Permission checks:** All write operations (rename, delete, add/remove media/members) require admin role. Permission checks MUST occur before any state changes.

3. **Default library protection:** Default library invariants are enforced at API level (400 errors) to prevent accidental violations.

4. **Visibility rule enforcement:** Social object subsystems MUST call visibility check functions defined in §4.2. They MUST NOT implement their own visibility logic.

---

## 8. Performance & Limits (v1)

- No explicit limits on libraries, members, or media in v1; rely on reasonable use.
- Keep pagination simple (offset-based; limit default 50, max 100); no further guarantees.
- Visibility checks must use the shared-library intersection rule and rely on indexes on LibraryMedia/LibraryUser to stay near O(1)/O(n_members) with p95 ≈10ms.
- Treat this spec as functional, not an SLO/metrics doc; detailed targets are deferred.

---

## 9. Observability

Minimal logging for v1:
- Log failed writes and permission denials.
- Optionally log library create/delete and media/member add/remove for debugging.
- Full structured logging, metrics, and alerting are deferred to post-v1.

---

## 10. Test Matrix

### 10. Testing & QA (focused)

- Unit/integration coverage MUST include:
  - Default library protection (no share/delete/rename).
  - Membership permissions (admin-only writes).
  - LibraryMedia uniqueness and add/remove behavior.
  - Default library auto-add on media attachment and member-join.
  - Default library removal cascade to owner's personal libraries.
  - Visibility rule intersection cases (shared vs disjoint libraries).
- Load/SLO testing and exhaustive error-code matrices are deferred.

### 10.2 Visibility Rule Tests

| Scenario                               | Setup                                               | Expected Result                                         | Rationale                      |
|----------------------------------------|-----------------------------------------------------|---------------------------------------------------------|--------------------------------|
| Viewer and owner share a library       | A and B both in library L with media M              | A sees B's highlights on M; B sees A's                 | Shared library intersection    |
| Viewer and owner only disjoint libs    | A in L1 with M, B in L2 with M, no shared library   | Neither sees the other's highlights on M               | No shared library ⇒ invisible  |
| Viewer lacks library with media        | A has no library with M, B has library with M       | A cannot see B's highlights on M                       | Viewer must share library      |
| Owner lacks library with media         | A has library with M, B has no library with M       | A cannot see B's highlights on M                       | Owner must share library       |
| Owner viewing own object               | A viewing own highlight on M                        | A can see own highlight regardless of libraries        | Owner can always see own       |

---

## 11. Open Questions

### Resolved (v1 decisions committed)

1. **Q:** Can owner leave non-default libraries?
   **A:** NO. Owner must remain a member/admin; owner cannot leave or demote.

2. **Q:** Can default library be renamed?
   **A:** YES. Rename is allowed (admin-only), even for default library.

3. **Q:** How do we handle removing media from default library?
   **A:** Remove from default library and from all of the owner's personal (sole-member) libraries.

4. **Q:** What happens when a library transitions from shared to unshared?
   **A:** No automatic action in v1 (shared→unshared auto-add is deferred).

### Open (require product decision before or during implementation)

**Non-blocking (can be decided during implementation):**

1. **Q:** What exactly happens if ownership transfer is needed?
   **A:** UNRESOLVED. v1 keeps owner immutable and always a member/admin. Ownership transfer is out of scope; add later if required.

2. **Q:** Should we allow renaming default library?
   **A:** UNRESOLVED. Domain model and PRD both state "default libraries cannot be renamed (v1 product constraint)". This spec adopts the stricter rule (no rename). If product explicitly decides to allow rename:
   - Remove the `is_default` check in PATCH /libraries/{id}.
   - Update error codes accordingly.

**Product-level questions (impact UX):**

5. **Q:** Should we support library "kinds" (e.g., course library, org library, personal library)?
   **A:** OUT OF SCOPE for v1. Future extension: add `library.kind` enum field.

6. **Q:** Should we support public/discoverable libraries?
   **A:** OUT OF SCOPE for v1. Future extension: add `library.visibility` enum (private, public, unlisted).

---

## 12. Future Extensions

**Potential post-v1 enhancements:**

1. **Ownership transfer:** Allow owner to transfer ownership to another admin (requires ownership transfer flow, confirmation, etc.).

2. **Invitation system:** Email invitations, pending invitations, accept/reject flow (currently, members are added directly by admin).

3. **Library discovery:** Search for public libraries, browse by topic, join public libraries.

4. **Public libraries:** Libraries visible to all users, with read-only or read-write access.

5. **Per-media visibility flags:** Private documents (media not globally readable), library-scoped media (media only visible to library members).

6. **Library kinds:** Course libraries, organization libraries, team libraries (with different permission models).

7. **Advanced roles:** Reader (read-only), contributor (can add media but not members), etc.

8. **Library templates:** Pre-populated libraries for common use cases (e.g., "Book Club" with suggested reading list).

9. **Library analytics:** Most-read media, most-highlighted passages, member activity.

10. **Batch operations:** Add/remove multiple media or members in one request.

11. **Library archiving:** Soft-delete libraries (hide from view but preserve data).

12. **User groups:** Add entire groups (e.g., "CS101 students") to libraries.

13. **Notification system:** Notify members when media/members are added/removed.

14. **Audit log:** Track all library operations for compliance/debugging.

**Critical future rearchitecture (if per-media visibility is needed):**
- Add `media.visibility` enum (global, private, library-scoped).
- Rework deduplication (duplicate content for different users if private).
- Add access control layer (media read checks, not just social object visibility).
- Significant complexity increase; only pursue if v1 product stance ("public corpus") proves unworkable.

---

## End of Specification

**Status: IMPLEMENTATION-READY**

This document defines the complete interface contract and invariants for the libraries, permissions, and visibility subsystem. It is implementation-ready with the following caveats:

1. **Open questions in §11 should be resolved before or during implementation** (non-blocking; reasonable defaults are specified).
2. **Social object subsystems** (highlights, annotations, conversations) MUST use visibility check functions defined in §4.2; they MUST NOT implement their own visibility logic.
3. **Search subsystem** MUST enforce visibility rules defined in §6.4 when returning social object results.

**Post-implementation validation:**
- All invariants in §6 MUST be enforced by tests in §10.
- All error codes in §7 MUST be covered by integration tests.
- Visibility rule tests in §10.2 MUST pass (especially disjoint library cases).
- Basic performance guidance in §8 SHOULD be met (keep visibility checks indexed and fast).

**Deviations from invariants are forbidden.** Ambiguities MUST be escalated to product owner.
