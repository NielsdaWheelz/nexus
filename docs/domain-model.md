# Nexus Domain Model

## 1. Purpose

This document is the single source of truth for the Nexus domain model. It defines all entities, relationships, invariants, lifecycles, visibility rules, and canonical text/highlighting semantics. All backend implementations must conform to this specification.

---

## 2. Entities

### User

- Represents an authenticated user of the system.
- Essential attributes: id, email, display_name, subscription_tier, stripe_customer_id, created_at, updated_at.
- subscription_tier enum: `free`, `personal` (pro deferred to future).
- stripe_customer_id: nullable; populated when user creates Stripe customer record.

### Subscription

- Represents a user's subscription state and Stripe billing details.
- Essential attributes: id, user_id, stripe_subscription_id, stripe_price_id, status, current_period_start, current_period_end, cancel_at_period_end, created_at, updated_at.
- status enum (simplified v1): `active`, `past_due`, `unpaid`, `incomplete`, `canceled` (any non-active is treated as not-paid for entitlements).
- stripe_subscription_id: Stripe's subscription object ID.
- stripe_price_id: Stripe's price ID (identifies tier: personal; pro reserved for future).
- Constraint: At most one active-ish subscription per user (statuses in {active, past_due, unpaid, incomplete}); historical rows allowed; free users may have zero subscriptions.

### UsageRecord

- Tracks daily LLM message usage for quota enforcement.
- Essential attributes: id, user_id, date, message_count, created_at, updated_at.
- date: UTC date (YYYY-MM-DD).
- message_count: number of user messages sent (not assistant responses).
- Constraint: One record per (user_id, date).

### Library

- A collection of media owned by a user.
- Essential attributes: id, name, owner_user_id, is_default, created_at, updated_at.
- Constraint: Each user has exactly one library where is_default = true.
- owner_user_id is immutable except via explicit ownership transfer operation. Ownership cannot be transferred for default libraries.

### LibraryUser

- Membership relation between users and libraries.
- Essential attributes: library_id, user_id, role.
- Roles: `member`, `admin`.
- Constraint: Owner always appears as a row in LibraryUser with role='admin'. Owners cannot leave their own libraries; changing ownership requires an explicit transfer operation or deletion of the library (not allowed for default libraries).

### Media

- A globally deduplicated content item.
- Kinds in v1: `html`, `epub`, `pdf`.
- Essential attributes: id, kind, canonical_url, source, uploader_user_id, content_hash, html, plain_text, storage_path, processing_status, failure_reason, created_at, updated_at, processing_started_at, processing_completed_at.
- processing_status enum: `pending`, `processing`, `ready_for_reading`, `indexed`, `failed`.
- source enum: `upload`, `url`.
  - If source='upload': storage_path NOT NULL, canonical_url NULL
  - If source='url': canonical_url NOT NULL, storage_path MAY be NULL
- content_hash: SHA-256 hash, primary deduplication key (unique constraint)
- canonical_url: metadata only, NOT a deduplication key

### LibraryMedia

- Association between a library and media.
- Essential attributes: library_id, media_id, added_at.

### Author

- A globally deduplicated author entity.
- Essential attributes: id, name, created_at.

**Author Subsystem Ownership (Clarified):**

Authors are managed by multiple subsystems with distinct responsibilities:

**Ingestion subsystem (v1):**
- Best-effort extraction from document metadata during ingestion (HTML `<meta>`, EPUB `<dc:creator>`)
- Automatic creation of `author` rows (exact string match, no normalization)
- Splitting author strings on separators (comma, " and ", " & ")
- Insert-only: NEVER updates or deletes existing author rows
- This creates a messy author table with low-quality entries ("NYTimes Staff", "Unknown", "–")
- Naive splitting produces garbage (e.g., "Smith, John and Jane Doe" → 3 entries)

**User-initiated metadata entry (v1):**
- Users can manually create authors via UI (for missing/incorrect metadata)
- Create-only: users CANNOT edit or delete authors in v1

**Metadata subsystem (future, post-v1):**
- Will own comprehensive author management (editing, merging, disambiguation)
- May use LLM or external APIs for normalization
- Out of scope for v1

**Constraints:**
- v1 uses exact string match for deduplication; no normalization or disambiguation
- Media may have zero authors; absence is allowed and does not block processing
- Author correctness is not guaranteed in v1; expect low data quality

### MediaAuthor

- Association between media and authors.
- Essential attributes: media_id, author_id.
- Constraint: (media_id, author_id) is unique.

### Chunk

- A segment of media content for a given chunking strategy.
- Essential attributes: id, media_id, chunking_strategy, sequence_index, content, embedding, created_at.
- chunking_strategy is an enum-like string; v1 default: `recursive_character`.
- embedding is stored as a pgvector type and indexed for ANN (approximate nearest neighbor) search.
- Constraint: For each (media_id, chunking_strategy), either zero chunks exist or a complete, consistent chunk set exists.

### Conversation

- A thread of messages owned by one user.
- Essential attributes: id, owner_user_id, title, created_at, updated_at.

### Message

- A single message within a conversation.
- Essential attributes: id, conversation_id, role, content, created_at.
- role enum in v1: `user`, `assistant`. Tool messages and system metadata are out-of-band, not first-class Message rows.
- Constraint: Messages have strictly increasing creation order within a conversation.

### MessageContext

- Links a message to referenced entities.
- Essential attributes: id, message_id, context_type, context_id.
- context_type: `media`, `highlight`, `annotation`, `conversation`, `message`.
- Multiple contexts per message allowed. Many messages may reference the same context target.

### Highlight

- A text span selection by a user on a media item.
- Offsets (`start_offset`, `end_offset`) are 0-indexed character positions into `media.plain_text`, the canonical linear text derived deterministically from the processed display DOM (HTML/EPUB) or pdf.js text layer (PDF).
- Backend stores only canonical offsets; no DOM offsets or PDF coordinates are persisted.
- Essential attributes: id, user_id, media_id, start_offset, end_offset, quote, prefix, suffix, color, created_at, updated_at.
- Constraint: (user_id, media_id, start_offset, end_offset) is unique.
- Overlapping highlights for the same user are allowed.

### Annotation

- A note attached to a highlight.
- Essential attributes: id, highlight_id, body, created_at, updated_at.
- Constraint: Annotations can only exist if attached to a highlight. Highlights can exist without annotations.

---

## 3. Relationships & Cardinality

| Relationship | Cardinality | Directionality | Uniqueness |
|--------------|-------------|----------------|------------|
| User → Subscription | 1–0..1 | User has Subscription | Each subscription belongs to one user |
| User → UsageRecord | 1–many | User has UsageRecords | (user_id, date) unique |
| User → Library (ownership) | 1–many | User owns Libraries | Each library has one owner |
| User ↔ Library (membership via LibraryUser) | many–many | Bidirectional | (user_id, library_id) unique |
| Library → Media (via LibraryMedia) | many–many | Bidirectional | (library_id, media_id) unique |
| Media → Author (via MediaAuthor) | many–many | Bidirectional | (media_id, author_id) unique |
| Media → Chunk | 1–many | Media has Chunks | (media_id, chunking_strategy, sequence_index) unique |
| User → Conversation | 1–many | User owns Conversations | Each conversation has one owner |
| Conversation → Message | 1–many | Conversation contains Messages | Each message belongs to one conversation |
| Message → MessageContext | 1–many | Message has Contexts | Each context belongs to one message |
| User → Highlight | 1–many | User creates Highlights | Each highlight belongs to one user |
| Media → Highlight | 1–many | Media has Highlights | Each highlight references one media |
| Highlight → Annotation | 1–0..1 | Highlight may have Annotation | Each annotation belongs to exactly one highlight |

---

## 4. Visibility & Access Rules

### Media Visibility

- Media is globally readable. Any authenticated user can read any media in the system, regardless of library membership.
- **Product consequence:** This creates a "public corpus, private annotations" model. All media forms a global catalog visible to all users; only the social layer (highlights, annotations, conversations) is privacy-scoped.

### Social Object Visibility

Social objects are: highlights, annotations, messages, conversations.

A user may see a social object if and only if:
- They are the owner, OR
- They share at least one library with the owner containing the referenced media.

**Important:** Highlights, annotations, and messages are global per (user, media); library membership only gates visibility, not where the object was created. A user's highlights on media M are visible to anyone who shares any library containing M with that user.

### Key Consequences

- Two users with the same media in unrelated libraries cannot see each other's highlights.
- Once a user can see any message from conversation C (via the shared-media rule), they can see all messages in conversation C, even if some messages reference media that are not shared with them. There is no per-message privacy within a partially-shared conversation in v1.
- If user A adds media M to a shared library with user B, all of A's highlights on M (including those created in private contexts) become visible to B, and all of B's highlights on M (including those created in private contexts) become visible to A.
- If a user removes media M from all their libraries (including default), they still see their own highlights/annotations/conversations on M (via the owner rule), but M no longer appears in their library views. M remains accessible via the global media catalog.
- Search must enforce these visibility rules.
- Search returns: media (global), social objects (visibility-scoped).

### Library Visibility

- Libraries are invisible to non-members.
- Only owners and admins can: rename library, add/remove media, invite/remove members, change roles.

---

## 5. Invariants

### User Invariants

- Each user has exactly one default library (is_default = true).
- Users start with subscription_tier = 'free' on registration.
- stripe_customer_id is null until user initiates first payment flow.

### Subscription Invariants

- A user can have at most one active-ish subscription (statuses in {active, past_due, unpaid, incomplete}) at any time.
- Free tier users may have zero subscriptions; if a subscription exists and is not active, the tier must be free.
- Subscription status synchronizes with Stripe webhooks.
- Entitlements: only `active` yields paid tier; all other statuses map to free immediately (no grace in v1).
- Downgrade enforcement: user cannot add new media to default library if over tier limit; existing media remains readable.

### Usage Invariants

- UsageRecords track daily LLM message counts for quota enforcement.
- message_count increments only for user messages, not assistant responses.
- Daily reset at midnight UTC (new date → new UsageRecord).
- Quota enforcement (v1):
  - Free tier: 10 messages per day
  - Personal tier: 50 messages per day
  - Pro tier: 100 messages per day (pro deferred; treat as future extension)
- Exceeding quota prompts upgrade flow or "wait until tomorrow" message.

### Library Invariants

- A library is considered shared if and only if it has more than one LibraryUser row.
- The owner of a library MUST always be a member of that library with role='admin'. An owner who is not a member is not allowed. Other members may be promoted to admin by existing admins; owner cannot be demoted.
- Owner cannot leave the library without transferring ownership or deleting it. Default libraries cannot be deleted and ownership cannot be transferred.
- Default libraries must have exactly one LibraryUser row (the owner). Default libraries are never shareable; attempts to add other users as members must be rejected at the API level.
- Default libraries may be renamed; rename is admin-only (owner).
- Default library holds media the user explicitly adds or uploads; joining a shared library does NOT auto-import that library’s media into the user’s default.
- When a user explicitly adds media M to any library they are a member of (including uploads they initiate), M is automatically added to their default library.
- Removing media from default library removes it from all unshared libraries owned by that user (member_count == 1).

### Media Invariants

**Deduplication (Strict Content-Based):**
- Media is globally deduplicated by `content_hash` (SHA-256 of raw bytes)
- Unique constraint on `media(content_hash)` enforces strict deduplication at database level
- All `content_hash` values MUST be populated (no NULL allowed in v1)
- Two media rows with identical `content_hash` MUST NOT exist (database-enforced)
- Deduplication is strict and deterministic: identical bytes always map to the same media_id
- `canonical_url` is metadata only, NOT a deduplication key:
  - Multiple different URLs MAY map to same media_id (if content identical)
  - Multiple different media_id MAY have identical canonical_url (if content differs)
- **Product-level deduplication semantics:**
  - "No duplicate documents" means "no two rows with identical bytes" (guaranteed)
  - Does NOT mean "no two rows that are conceptually the same text" (best-effort only)
  - Cannot prevent logical duplicates (same article with different HTML formatting)
- First upload of content is canonical; v1 does not support content updates or re-ingestion
- Upload deduplication: if media already exists (content_hash match), add it to user's library rather than creating a new media record

**Other invariants:**
- Media cannot be deleted by users; they can only remove it from their libraries
- User can read media once processing_status reaches `ready_for_reading`
- Semantic search is available once processing_status reaches `indexed`
- **Tier limits on media count in default library (enforced by quota/billing subsystem, not ingestion):**
  - Free tier: maximum 5 media in default library
  - Personal tier: unlimited media
  - Pro tier: unlimited media (pro deferred; treated as future extension)
- Attempting to add media beyond tier limit prompts upgrade flow
- Limits apply at default library level (explicitly added/uploaded media only; shared-library membership alone does not auto-add)

### Chunk Invariants

- For each (media_id, chunking_strategy): either zero chunks exist, or a complete consistent chunk set exists.
- Re-chunking must delete all previous chunks for that (media_id, chunking_strategy) first.

### Highlight Invariants

- Canonical text: `media.plain_text` is the single source for all offsets; it is deterministic, derived from the processed display DOM (HTML/EPUB) or pdf.js text layer (PDF), and is immutable once processing_status reaches `ready_for_reading`.
- All highlight offsets index into `media.plain_text` only; backend does not store DOM offsets or PDF coordinates.
- A user cannot create two highlights with identical (media_id, start_offset, end_offset).
- Overlapping highlights for the same user are allowed.

### Annotation Invariants

- Highlights can exist without annotations. Annotations can only exist if attached to a highlight.
- Deleting a highlight deletes its annotation (if one exists).
- Deleting an annotation leaves the highlight intact.
- Messages referencing a deleted highlight or annotation are not deleted; their MessageContext rows referencing that target are deleted. UI must handle "this note was deleted" gracefully if needed.

### Conversation & Message Invariants

- A conversation belongs to exactly one user.
- Only the owner may post messages; other users can read (if visibility allows) but cannot reply.
- All messages in a conversation belong to the same owner (the conversation owner).
- Messages belong to exactly one conversation.
- Messages have strictly increasing creation order.
- Message deletion removes its contexts; if it was the last message, the conversation is deleted.

### Deletion Invariants

- Hard delete for all social objects.
- No undelete mechanism in v1. No versioning or history tracking. This is a product choice, not an omission.

---

## 6. Lifecycles & State Machines

### Media Ingestion Lifecycle

```
┌─────────┐     ┌────────────┐     ┌───────────────────┐     ┌─────────┐
│ pending │ ──▶ │ processing │ ──▶ │ ready_for_reading │ ──▶ │ indexed │
└─────────┘     └────────────┘     └───────────────────┘     └─────────┘
                      │
                      │              ┌────────┐
                      └────────────▶ │ failed │
                                     └────────┘
```

- **pending**: Media record created, awaiting processing.
- **processing**: Extraction and transformation in progress (extracting text, generating HTML).
- **ready_for_reading**: Text extraction complete; user can read media. Chunking and embedding in progress.
- **indexed**: Chunking and embedding complete; media is fully searchable via semantic search.
- **failed**: Processing failed at any stage; failure_reason populated.

State transitions:
- `pending` → `processing`: Processing job started
- `processing` → `ready_for_reading`: Text extraction completed successfully
- `ready_for_reading` → `indexed`: Chunking and embedding completed successfully
- `processing` → `failed`: Extraction failed
- `ready_for_reading` → `failed`: Chunking/embedding failed (rare, but possible)

Retry behavior:
- Retries reset status to `pending`.
- Retries delete any partial chunks and embeddings before reprocessing.

### Highlight Lifecycle

```
┌─────────┐     ┌─────────┐
│ created │ ──▶ │ deleted │
└─────────┘     └─────────┘
```

- Created when user selects text and confirms highlight.
- Deleted via hard delete. Deleting a highlight also deletes its annotation (if one exists). References from messages are not deleted.

### Annotation Lifecycle

```
┌─────────┐     ┌─────────┐
│ created │ ──▶ │ deleted │
└─────────┘     └─────────┘
```

- Created when user adds a note to a highlight.
- Deleting an annotation removes the note but leaves the highlight intact.

### Conversation Lifecycle

```
┌─────────┐     ┌─────────┐
│ created │ ──▶ │ deleted │
└─────────┘     └─────────┘
```

- Created when user starts a new conversation.
- Deleted when the last message is deleted.

### Message Lifecycle

```
┌─────────┐     ┌─────────┐
│ created │ ──▶ │ deleted │
└─────────┘     └─────────┘
```

- Created when owner posts to conversation.
- Deletion removes all associated MessageContext records.
- If it was the last message, conversation is cascade deleted.

### Subscription Lifecycle

```
        ┌────────────┐
        │   active   │
        └──────┬─────┘
               │
               ▼
┌────────────┬────────────┬───────────┐
│ incomplete │  past_due  │  unpaid   │
└────────────┴────────────┴───────────┘
               │
               ▼
          ┌────────────┐
          │  canceled  │
          └────────────┘
```

- **active**: Subscription is current; user has full paid tier access.
- **incomplete**: Initial payment incomplete (new subscription not yet activated). Entitlement = free.
- **past_due**: Payment failed; retrying. Entitlement = free.
- **unpaid**: Payment failed after retries. Entitlement = free.
- **canceled**: User canceled or payment failed. Entitlement = free.

State transitions:
- User subscribes → `incomplete` (if payment pending) or `active` (if payment succeeds immediately).
- Payment succeeds → `active`.
- Payment fails → `past_due`; further failure → `unpaid`; cancellation webhook → `canceled`.
- Any non-`active` status maps entitlements to free immediately (no grace).
- User cancels → `canceled` (period-end handling may exist in Stripe but entitlements become free on non-active).

Stripe webhook synchronization:
- Subscription status changes are pushed via Stripe webhooks
- Webhooks update subscription.status and user.subscription_tier
- System enforces tier limits based on user.subscription_tier (which is derived from status)

---

## 7. Canonical Text & Highlight Model

### Canonical Text Definition

- `media.plain_text` is the canonical linear text representation of the media.
- All character offsets, chunking, embeddings, search indices, and highlight ranges are measured against `plain_text`.
- For HTML/EPUB media:
  - `media.html` is the "clean reading HTML" produced at ingestion (article content only, no ads/navigation/chrome).
  - `media.plain_text` is a deterministic linearization of `media.html` in document order.
  - The reader subsystem MUST render highlights and perform text selection using the DOM derived from `media.html` (not by re-running extraction or re-fetching the URL).
  - This guarantees that highlight offsets into `plain_text` map correctly to the rendered DOM.
- For PDF media:
  - `media.plain_text` is extracted from the PDF at ingestion using deterministic text extraction in reading order.
  - `media.html` is NULL (PDF rendering uses pdf.js on frontend).
  - The reader subsystem MUST use the pdf.js text layer for offset mapping and highlighting.
  - For PDFs without text layers (scanned/image-only): `plain_text` is empty, highlighting is disallowed by reader subsystem, and semantic search is unavailable.
- **Invariant:** For media with `plain_text` empty, highlight creation MUST be disallowed by reader subsystem (not ingestion), and chunking/embedding MUST NOT run. Such media remain `ready_for_reading` but never transition to `indexed`.

### Offset Model

- Highlights store `start_offset` and `end_offset` as 0-indexed character positions into `plain_text`.
- Offsets are inclusive of start, exclusive of end: `[start_offset, end_offset)`.
- Highlights also store `quote` (the selected text), `prefix` (30 characters before), and `suffix` (30 characters after) for anchoring.

### Mapping Process (Contract)

The frontend is responsible for mapping offsets to renderable DOM ranges:

1. **Text Node Traversal**: Walk the rendered DOM to build a mapping from cumulative character offset to text nodes.
2. **Offset Resolution**: Given (start_offset, end_offset), locate the corresponding text nodes and intra-node offsets.
3. **Range Construction**: Create a DOM Range spanning the resolved positions.

### HTML Rendering

- Segment text nodes at highlight boundaries.
- Wrap minimal segments in `<mark>` elements with appropriate styling.
- Overlapping highlights are rendered by segmenting text into minimal non-overlapping spans and wrapping those spans in `<mark>` elements annotated with all covering highlight IDs.

### PDF Rendering

- For PDF media, `plain_text` is derived from the pdf.js text layer in reading order, using the same traversal logic as in the HTML case. The pdf.js text layer DOM is treated as the rendering of `plain_text`.
- Offsets map to the pdf.js text layer content.
- Frontend renders overlay rectangles positioned over the text layer.
- Overlays are non-invasive; they do not modify the PDF internals.
- Highlights are re-rendered on text layer render and scale change events.

### Future: Transcripts

- For transcripts, `plain_text` contains the transcript text.
- The highlight model is identical to HTML: offsets into `plain_text`, frontend maps to rendered transcript DOM.

---

## 8. Search Model

### Semantic Search

- Operates over `Chunk.embedding` using pgvector ANN (approximate nearest neighbor) queries.
- Returns chunks ranked by similarity; chunks are grouped by media for result presentation.
- Semantic search operates over all media in the system (since media is globally readable).
- Social objects attached to those media are filtered by visibility rules.

### Keyword Search

- Operates over text fields: `media.plain_text`, `media.title`, `author.name`, `message.content`, `annotation.body`.
- Uses full-text search capabilities (e.g., PostgreSQL `tsvector`/`tsquery` or trigram indexes).
- Returns matching entities ranked by relevance.

### Search Results

Search can return the following entity types:
- **Media** (globally readable)
- **Highlights** (visibility-scoped: owner OR shared library with media)
- **Annotations** (visibility-scoped: owner OR shared library with media)
- **Messages** (visibility-scoped: owner OR shared library with referenced media)
- **Conversations** (visibility-scoped: same as messages within)

All results must enforce visibility rules as defined in section 4.

**Result Navigation:**
- Selecting a message result MUST open the conversation and scroll to that specific message.
- Selecting a conversation result MUST open the conversation and scroll to the last message.

### Implementation Notes

- Search indices are built from `plain_text` and other canonical text fields.
- Semantic search is only available for media with `processing_status = 'indexed'`.
- Keyword search is available for media with `processing_status >= 'ready_for_reading'`.
- Hybrid search (combining semantic + keyword) ranks results using a weighted score.

---

## 9. Future Extensions

The following entities are not part of v1 but the domain model anticipates their addition:

- **Podcasts**: A container for podcast metadata and episodes.
- **Episodes**: Individual podcast episodes with associated media.
- **Videos**: Video content with timeline-based highlights.
- **Linking Graph**: Relationships between media items.
- **Transcripts**: Time-coded text representations of audio/video content, using the same canonical text and highlight model.

These extensions will follow the same patterns established in v1: global deduplication, visibility rules based on library membership, and offset-based highlighting into canonical text.
