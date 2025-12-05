# Nexus Subsystem Spec: Conversations & LLM

## 1. Scope

This spec defines the conversations + LLM subsystem: lifecycle of `conversation`, `message`, and `message_context`; quote-to-chat flows; follow-up messaging; LLM prompt orchestration; quota enforcement; visibility; HTTP APIs; error handling; and deletion semantics.

**In scope (v1):**
- Conversation + Message lifecycle: create via quote-to-chat, list, read, delete; optional title update only.
- Message roles: `user`, `assistant` (no `system/tool` rows in v1; system prompt is runtime metadata).
- Quote-to-chat: start from an existing `highlight_id`; create conversation, first user message, message_context rows; generate assistant reply.
- Follow-up messaging in existing conversation (owner only) with LLM response; optional single highlight context.
- Visibility: single-owner conversations; non-owners may read if they can see any message via media-linked visibility (shared-library rule); once admitted, they see all messages in the conversation.
- MessageContext management: media/highlight/annotation references only (no conversation/message contexts in v1).
- Usage/billing integration: enforce daily LLM quota per subscription tier; increment `UsageRecord` only when an LLM call is performed; over-quota still persists the user message but skips LLM.
- LLM orchestration: prompt construction inputs (quote via highlight, surrounding media.plain_text context, conversation history, media metadata); synchronous (non-streaming) HTTP flow for v1.
- HTTP APIs: quote-to-chat, send message, list conversations, fetch conversation with messages, delete message (with cascade delete of conversation when last message removed).

**Explicitly out of scope (v1):**
- Per-message or per-turn privacy controls (no “private reply” in shared conversation).
- Multi-user conversations or DMs/groups (exactly one owner per conversation).
- Streaming responses.
- Persisted system prompts as Message rows (system metadata is out-of-band).
- LLM auto-summarization of conversations.
- LLM tools/function-calling.
- Search behavior (shape only; search subsystem enforces visibility).
- UI layout/UX.

## 2. Dependencies

Entities and fields used (read/write as noted):
- **User:** `id`, `subscription_tier` (read for quota tier).
- **UsageRecord:** `user_id`, `date`, `message_count` (read/write for quota accounting).
- **Media:** `id`, `plain_text`, `title`, `processing_status` (read; require `ready_for_reading`+ for quote-to-chat; plain_text for context).
- **Highlight:** `id`, `media_id`, `user_id`, `start_offset`, `end_offset`, `quote` (read to attach context).
- **Annotation:** `id`, `highlight_id`, `body` (read to attach context).
- **Conversation:** `id`, `owner_user_id`, `title`, timestamps (full lifecycle).
- **Message:** `id`, `conversation_id`, `role`, `content`, timestamps (full lifecycle).
- **MessageContext:** `id`, `message_id`, `context_type`, `context_id` (full lifecycle; context_type limited to media/highlight/annotation in v1).

Authoritative visibility rule (from `spec-libraries-permissions-visibility.md`):
```
can_see_social_object(viewer, owner, media) ⟺ (viewer = owner) ∨ (∃ library L: viewer ∈ L ∧ owner ∈ L ∧ media ∈ L)
```
This spec MUST call shared helpers and MUST NOT reimplement visibility logic.

Other spec dependencies:
- **spec-billing-subscriptions-usage.md:** daily LLM quotas per tier; atomic `UsageRecord` increment and read/modify/write safeguards.
- **spec-canonical-text-highlights-annotations.md:** canonical offsets and highlight/annotation validity; quote-to-chat must honor offset semantics.
- **spec-ingestion.md:** `Media.processing_status` and `plain_text` availability; disallow quote-to-chat if media not `ready_for_reading` or plain_text empty.
- **spec-chunking-search-index.md:** search may surface conversations/messages; this spec defines visibility and shapes only.

## 3. Responsibilities

**Must do:**
1) Own Conversation/Message lifecycle: create, read, delete; allow title update (optional); no other Message updates.
2) Manage MessageContext rows: validate targets exist and types match; attach contexts for quote-to-chat messages (media + highlight + optional annotation).
3) Enforce ownership rules: exactly one owner per conversation; only owner can send messages; all messages in a conversation share the owner.
4) Enforce visibility: non-owner can read a conversation iff they can see at least one message via media-based visibility; once admitted, they see all messages in that conversation.
5) LLM orchestration: when owner sends a user message in an LLM-enabled conversation, build prompt, call LLM, create assistant message (synchronous in v1).
6) Quota enforcement: for each role=`user` message, persist the user message; if within quota, atomically check/increment UsageRecord and call LLM; if over limit, do not call LLM, return error, leave UsageRecord unchanged.
7) Error surfaces: clear error codes for quota exceeded, invalid context, forbidden, LLM failures/timeouts.
8) Deletion: deleting a message deletes its MessageContexts; deleting the last message deletes the conversation.

**Must not do:**
- Perform authentication beyond extracting current user.
- Reimplement visibility logic; must call shared helper.
- Create/modify media/highlights/annotations (only reference them; highlights are created via the highlights API).
- Implement search or indexing.
- Store library_id on conversation/message/context.
- Allow context_type outside {media, highlight, annotation} in v1.

## 4. External Interfaces

All endpoints require authentication; `current_user_id` from session/JWT. Content inputs are UTF-8 strings; max lengths noted in §8.

### 4.1 HTTP Endpoints (v1)

#### POST `/api/v1/conversations/from-highlight`
Purpose: Quote-to-chat entrypoint: create conversation + first user message + contexts + assistant reply.
Request:
```json
{ "highlight_id": "uuid", "message": "user content", "title": "optional" }
```
Rules:
- highlight_id required. Frontend flow: selection → create highlight via highlights API → call this endpoint.
- Highlight must exist and be owned by caller; its media must have `processing_status ∈ {ready_for_reading, indexed}` and `plain_text` non-empty.
- Owner = current user; conversation created; first message role=`user` with provided content; assistant reply created synchronously after LLM call.
- MessageContexts attached: `highlight` + its `media`; include `annotation` context if highlight has annotation.
Response: `201 Created`
```json
{
  "conversation": { "id": "uuid", "title": "...", "owner_user_id": "uuid" },
  "messages": [
    { "id": "uuid", "role": "user", "content": "user content", "contexts": [...] },
    { "id": "uuid", "role": "assistant", "content": "assistant reply", "contexts": [] }
  ]
}
```
Errors:
- `400 INVALID_CONTEXT` (bad offsets, empty message, media not ready, plain_text empty)
- `404 HIGHLIGHT_NOT_FOUND` / `MEDIA_NOT_FOUND`
- `401 UNAUTHORIZED`
- `429 LLM_QUOTA_EXCEEDED`
- `424 LLM_UNAVAILABLE` (provider/transport error)
- `504 LLM_TIMEOUT`
- `500 INTERNAL_ERROR`
Behavior on LLM failure (424/504): User message is persisted with contexts; assistant message is NOT created; response includes error_code and message_id for the user message to allow retry via send-message endpoint.

#### POST `/api/v1/conversations/{id}/messages`
Purpose: Send a new user message in an existing conversation; create assistant reply.
Request:
```json
{ "message": "user content", "highlight_id": "uuid | null" }
```
Rules:
- Only owner may send (403 if not).
- Conversation must exist.
- Optional single `highlight_id`; if provided, must be owned by caller; contexts attached: highlight + its media (+ annotation if present). If absent, message has zero contexts.
- Persist user message always. Quota enforcement is delegated to `check_and_maybe_increment_llm_usage` (billing spec); if allowed, increment there and call LLM; else skip LLM call and return `LLM_QUOTA_EXCEEDED` (429) with the created user message.
- LLM call synchronous; assistant message created on success.
Response: `201 Created`
```json
{
  "messages": [
    { "id": "uuid", "role": "user", "content": "...", "contexts": [...] },
    { "id": "uuid", "role": "assistant", "content": "...", "contexts": [] }
  ]
}
```
Errors: same as quote-to-chat plus `404 CONVERSATION_NOT_FOUND`, `403 CONV_FORBIDDEN` (non-owner), `400 INVALID_CONTEXT`.
LLM failure behavior: persist user message, no assistant message; return `424 LLM_UNAVAILABLE` or `504 LLM_TIMEOUT` with the user message payload.

#### GET `/api/v1/conversations`
Purpose: List conversations visible to current user.
Response: `200 OK`
```json
{
  "conversations": [
    { "id": "uuid", "title": "...", "owner_user_id": "uuid", "last_message_at": "...", "message_count": 5, "visibility": "owner|shared" }
  ],
  "cursor": "next-cursor",
  "has_more": true
}
```
Visibility:
- Include conversations owned by user.
- Include conversations where user can see any message via shared-library-with-media rule (see §5).
Pagination: cursor-based; order by `updated_at DESC, id DESC`.
Errors: `401 UNAUTHORIZED`.

#### GET `/api/v1/conversations/{id}`
Purpose: Fetch conversation metadata and full message list (ordered by created_at, id tiebreak).
Response: `200 OK`
```json
{ "conversation": {...}, "messages": [ { "id": "...", "role": "...", "content": "...", "contexts": [...] }, ... ] }
```
Visibility:
- Owner: always allowed.
- Non-owner: allowed only if can see at least one message in the conversation (per §5). If allowed, returns ALL messages (no per-message privacy).
Errors:
- `404 CONVERSATION_NOT_FOUND` (not found or not visible)
- `403 CONV_VISIBILITY_FORBIDDEN` (exists but viewer cannot see any message)
- `401 UNAUTHORIZED`
- Non-owners have no standalone `GET /messages/{id}` in v1; access is via this endpoint only.

#### DELETE `/api/v1/messages/{id}`
Purpose: Delete a message. Owner-only.
Rules:
- Only conversation owner may delete any message (user or assistant).
- Deletes associated MessageContext rows.
- If the deleted message was the last in the conversation, deletes the conversation.
Response: `204 No Content`
Errors:
- `404 MESSAGE_NOT_FOUND`
- `403 MESSAGE_DELETE_FORBIDDEN` (non-owner)
- `401 UNAUTHORIZED`

### 4.2 LLM Behavior (v1 decision)

- Mode: **Synchronous**. HTTP POST that creates a user message performs LLM call inline; response returns after assistant message is created or failure is signaled.
- Model/provider: configured via environment; must support non-streaming text completion.
- Prompt inputs:
  - System meta (out-of-band, not stored): role as reading companion; safety instructions.
  - Conversation history: last N messages (configurable; default 10 turns).
  - Quote/context: highlight quote, ±2,000 chars of surrounding `media.plain_text` (bounded by doc length), media title.
  - User message content.
- Output stored verbatim as assistant message content.
- Safety: truncate inputs to model token/window limits; if truncated, log and include `truncated=true` metadata (not persisted in schema; response surface).

### 4.3 Background Jobs

None in v1 (synchronous LLM). Future async generate_reply job is deferred (§12).

## 5. State & Lifecycles

### Conversation lifecycle
```
created ──┐
          └─▶ deleted (when last message deleted)
```
- Creation: via /conversations/from-highlight (first message).
- Deletion: only via deletion of last message.
- Invariants:
  - Exactly one `owner_user_id`.
  - All messages in conversation share same owner_user_id (see Message lifecycle).

### Message lifecycle
```
created ──┐
          └─▶ deleted (hard delete)
```
- Roles: `user`, `assistant`.
- Ordering: strictly by created_at (id tiebreak).
- Owner: message.owner = conversation.owner (implicit via conversation).
- Deletion: removes MessageContexts; if last message, conversation deleted.

### Visibility semantics
- Message visible to viewer if:
  - Viewer is conversation owner, OR
  - Message has at least one MessageContext with `context_type ∈ {media, highlight, annotation}` where `can_see_social_object(viewer, owner, media)` is true.
- Conversation visible to viewer if:
  - Viewer is owner, OR
  - Viewer can see **any** message in the conversation by the above rule.
- Once a conversation is visible, **all** messages are returned (even those without contexts or with contexts to non-shared media).
- No per-message privacy within a visible conversation.
- Non-owners have no per-message fetch API in v1; access is only via conversation fetch.
- Conversations with no visible contexts remain owner-only until a visible message exists.

## 6. Invariants

Local invariants (in addition to domain model):
1) Conversation has exactly one owner; owner cannot change in v1.
2) All messages in a conversation have `conversation_id = conversation.id` and owner = conversation.owner_user_id.
3) Message roles ∈ {`user`, `assistant`}.
4) Message ordering: (created_at, id) is strictly increasing; no backdating edits (messages are immutable after create).
5) MessageContext:
   - context_type ∈ {`media`, `highlight`, `annotation`} in v1 (others rejected).
   - context_id must reference existing row of matching type.
   - At most one highlight context per message in v1; zero contexts allowed.
6) Deletion:
   - Deleting a message deletes its MessageContexts.
   - Deleting the last message deletes the conversation.
   - If a referenced highlight/annotation is deleted, apply the behavior defined in the highlights/annotations spec; MessageContext rows are updated/deleted accordingly; messages remain.
7) Visibility: No message/conversation returned if viewer fails visibility rule; enforcement is server-side.
8) LLM usage: Every role=`user` message that triggers LLM must:
   - Atomically increment `UsageRecord.message_count` for (user_id, UTC date) only when LLM call is made.
   - Enforce per-tier daily limit; if over, persist user message but skip LLM and leave usage unchanged.

## 7. Error Handling

Error codes (status mapping):
- `CONVERSATION_NOT_FOUND` (404)
- `CONV_FORBIDDEN` (403) – non-owner attempting mutation
- `CONV_VISIBILITY_FORBIDDEN` (403) – viewer cannot see any messages in convo
- `MESSAGE_NOT_FOUND` (404)
- `MESSAGE_DELETE_FORBIDDEN` (403)
- `INVALID_CONTEXT` (400) – bad ids, mismatched types, media not ready
- `LLM_QUOTA_EXCEEDED` (429)
- `LLM_UNAVAILABLE` (424)
- `LLM_TIMEOUT` (504)
- `INVALID_TITLE` (400)
- `INVALID_MESSAGE` (400) – empty or exceeds length limit
- `UNAUTHORIZED` (401)
- `INTERNAL_ERROR` (500)

LLM failure behavior:
- User message persists even if LLM fails (424/504); assistant message is absent. Client may retry by re-sending same content (will re-hit quota).
- No synthetic “error” assistant messages are stored.

Deleted references:
- When a referenced highlight/annotation is deleted, follow the deletion semantics in the highlights/annotations spec (contexts updated/deleted per that contract). Messages remain; UI expected to show “referenced content deleted”.

## 8. Performance & Limits

- Max conversations per user: no hard cap in v1; list endpoint must paginate (default limit 20, max 100).
- Max messages per conversation: 10,000 (reject with 400 if exceeded).
- Max message content length: 8,000 chars (server-side validation).
- Max contexts per message: 1 highlight context (v1).
- LLM latency target: p95 < 8s end-to-end for send-message; timeout 15s.
- Rate limits (per user, recommended): POST message endpoints 30 req/min (429 outside scope but suggested).
- Context window: include last 10 messages; truncate `plain_text` context to 2,000 chars; total token budget bounded by model window (configurable).

## 9. Observability

Logs (structured):
- `conversation_created`, `conversation_deleted`
- `message_created` (role), `message_deleted`
- `message_visibility_denied` (viewer, convo_id)
- `llm_call_start`, `llm_call_success`, `llm_call_failure` (error_code, duration_ms, user_id, conversation_id, media_id if any, truncated flag)
- `quota_check` (result, user_id, date, count, limit)

Metrics (suggested names/labels):
- `conversations_created_total`
- `messages_created_total{role}`
- `messages_deleted_total`
- `llm_requests_total{status=success|timeout|unavailable|rejected_quota}`
- `llm_latency_ms` histogram
- `quota_checks_total{outcome=allowed|denied|error}`

## 10. Tests

Unit:
- Visibility helper usage: given library memberships + contexts, verify visibility outcomes (owner, shared, disjoint).
- Conversation/message invariants: single owner; message ordering; deletion cascades contexts; deleting last message deletes conversation.
- MessageContext validation: rejects invalid types/ids; accepts multiple contexts; cascade delete.
- Quota enforcement: over-limit persists user message, skips LLM call, returns error; UsageRecord increments only when LLM call is made.
- LLM failure: user message persists; no assistant message; error surfaced.

Integration:
- Quote-to-chat E2E from highlight: creates convo, user msg with media+highlight context, assistant reply; visibility for shared vs disjoint users.
- Follow-up send message: optional single highlight context; assistant reply created; over-quota persists user message and returns error without assistant.
- Visibility scenarios: two users share library with media → see conversation/messages; without shared library → cannot access; when shared library removed → non-owner loses access (404/403).
- Deletion: delete assistant/user message; delete last message deletes conversation; contexts removed.
- Quota exceeded path: persists user message, no assistant, returns `LLM_QUOTA_EXCEEDED` (429); no UsageRecord increment when over limit.
- LLM timeout/unavailable: user message persisted; assistant missing; error code returned.
- Highlight/annotation deletion after being referenced: contexts removed, conversation still retrievable.

## 11. Open Questions

- Should we allow custom conversation titles auto-generated from first message/media? (v1: optional user-provided only.)
- Exact prompt template and safety system prompt text (deployment-specific).
- Max history length for prompts (default 10 turns chosen; adjust if costs too high).
- Should assistant messages be deletable by owner? (v1: yes; documented; confirm product expectation.)

## 12. Future Extensions

- Async LLM via background `generate_reply` job + webhook/polling; streaming responses.
- Multi-user/group conversations; per-message privacy; role diversification (system/tool).
- Persisted system prompts and per-conversation LLM settings (model, temperature).
- Conversation summarization and memory distillation.
- Tool/function-calling for retrieval or actions.
- Search over conversations/messages (deferred to search spec).
- Inline citations to media spans with structured context payloads.
- Rate limiting with adaptive backoff and user-facing retry-after.


