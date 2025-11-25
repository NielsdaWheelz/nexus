# Schema: Libraries, Memberships, Visibility

## 1. Libraries Table

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
CREATE INDEX idx_libraries_public ON libraries(is_public) WHERE is_public = TRUE;
```

## 2. Library Memberships Table

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
CREATE INDEX idx_library_memberships_library ON library_memberships(library_id);
```

## 3. Library Media Table

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

## 4. Object Library Visibility Table

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

## Visibility Rules Summary

**Documents**: Visible if user is member of library containing it

**Highlights**: Visible if:
- Media is visible, AND
- User is owner, OR highlight is public, OR highlight is shared to user's library

**Annotations**: Visible if highlight is visible

**Conversations**: Visible if user is owner, is public, or is shared to user's library

**Messages**: Visible if conversation is visible AND (user is owner, message is public, or message is shared)

