# Schema: Conversations, Messages, Summaries

## 1. Conversations Table

```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  title TEXT NOT NULL,
  description TEXT,

  -- Summary state (Phase 2+)
  summary_state TEXT,
  summary_updated_at TIMESTAMPTZ,

  -- Visibility
  is_public BOOLEAN NOT NULL DEFAULT FALSE,

  deleted_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_user ON conversations(user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_conversations_public ON conversations(is_public) WHERE is_public = TRUE AND deleted_at IS NULL;
```

## 2. Messages Table

```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,

  -- Model used (for assistant messages)
  effective_model_id TEXT,

  -- Token count (for budget tracking)
  token_count INTEGER,

  -- Visibility
  is_public BOOLEAN NOT NULL DEFAULT FALSE,

  deleted_at TIMESTAMPTZ,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_messages_user ON messages(user_id) WHERE deleted_at IS NULL;
```

## 3. Conversation Summaries (stored in conversations.summary_state)

**Structure**:

```json
{
  "text": "Conversation summary in 2-3 paragraphs...",
  "created_at": "2024-11-25T10:00:00Z",
  "message_count": 50,
  "latest_message_id": "uuid"
}
```

