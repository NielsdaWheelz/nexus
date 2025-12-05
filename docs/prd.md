# Nexus v1 PRD

## 1. Product Overview

Nexus is a collaborative reading and annotation platform that enables users to collect, read, highlight, and discuss web articles, EPUBs, and PDFs in one unified interface. It combines personal knowledge management with social reading features, allowing users to build personal libraries, share collections with reading groups, and engage in AI-assisted conversations about their reading material.

### v1 Scope

**In Scope:**
- User authentication and account management
- Media ingestion for HTML, EPUB, and PDF formats
- Personal and shared library management
- Reading interface with unified highlighting and annotation across all media types
- Visibility-scoped social features (seeing highlights/annotations from library members)
- Semantic and keyword search across media and social objects
- Quote-to-chat LLM conversations with media context

**Out of Scope for v1:**
- Podcasts, video, and transcript media types
- Linking graph relationships between media
- Ownership transfer for libraries
- Mobile applications (web-first)
- Metadata repair or auto-summarization via LLM
- Offline reading support

---

## 2. Personas & Core Jobs

### Solo Reader

A user who primarily uses Nexus for personal knowledge management and reading.

**Jobs to be Done:**
- Save articles, EPUBs, and PDFs from the web to read later
- Read content in a clean, distraction-free interface
- Highlight important passages and add notes for future reference
- Search across all saved content and personal annotations
- Ask questions about reading material and get AI-assisted answers
- Organize content into topical collections (libraries)

### Small Reading Group

A group of 2-30 users who read and discuss content together (e.g., book clubs, research teams, study groups).

**Jobs to be Done:**
- Share a curated collection of reading material with group members
- See what passages other group members found important
- Read others' annotations and thoughts on shared content
- Discover relevant content through group members' libraries
- Search across the group's collective highlights and notes
- Discuss specific passages with group members via AI-assisted chat

---

## 3. Core Workflows (Happy Paths)

### 3.1 Upload + Ingestion

**User Story:** As a user, I want to add content to my library so I can read and annotate it later.

**Flow:**
1. User provides a URL or uploads a file (EPUB, PDF)
2. System checks for existing media (deduplication)
3. If new: creates media record in `pending` status, adds to user's default library
4. If existing: adds existing media to user's default library
5. Processing pipeline extracts content, generates `plain_text` and `html`
6. Status transitions: `pending` → `processing` → `ready_for_reading` → `indexed`
7. User can read media once `ready_for_reading`
8. Semantic search available once `indexed`

**Acceptance Criteria:**
- User can upload via URL, file upload (drag-drop or file picker)
- Duplicate content is detected and reused (not re-ingested)
- Media automatically appears in user's default library
- Processing status is visible to user (pending, processing, ready_for_reading, indexed, failed)
- When media reaches `ready_for_reading`, user can read content (but semantic search may not be available yet)
- When media reaches `indexed`, semantic search is available
- UI MUST indicate current indexing state: "Reading ready, indexing..." or "Fully indexed"
- Failed ingestion displays `failure_reason` to user
- User can retry failed ingestion
- For web/EPUB content, Nexus automatically attempts to extract titles and authors from document metadata, so most items require no manual metadata entry
- For PDFs, title/author extraction is best-effort and may be missing or incorrect in v1

**CRITICAL PRODUCT DECISION: Scanned PDFs (No Text Layer)**

For PDFs without text layers (scanned/image-only), ingestion produces `plain_text = ''` (empty string).

**Technical behavior (defined by ingestion spec):**
- Media transitions to `ready_for_reading` (user can view visually)
- No chunking/embedding (no text to process)
- Media never transitions to `indexed`

**Product decisions (must be implemented by reader/search subsystems):**
- Reading: Visual rendering supported (user can view PDF)
- Highlighting: MUST be disabled (no text to anchor to)
- Search: Semantic search unavailable; keyword search unavailable
- Future: OCR support deferred to v2+

**User experience:**
- Clear indicator that "this PDF is view-only (no text layer)"
- Upload succeeds (not rejected)
- User can view but cannot highlight or search within document
- Suggest re-uploading with OCR-processed version if user needs highlighting/search

**Constraints (from domain model):**
- Media kinds: `html`, `epub`, `pdf` only
- `processing_status` enum: `pending`, `processing`, `ready_for_reading`, `indexed`, `failed`
- State transitions: `pending` → `processing` → `ready_for_reading` → `indexed`
- Failure can occur at any stage: `processing` → `failed` or `ready_for_reading` → `failed`
- Retries reset status to `pending` and delete partial chunks/embeddings
- Media added to any library is auto-added to default library
- Deduplication is content-based (content_hash), not URL-based; first upload is canonical
- v1 does not support content updates or re-ingestion

**Visible States:**
- Pending: "Queued for processing..." indicator
- Processing: "Extracting text..." indicator
- Ready for reading: "Reading ready, indexing for search..." indicator (user can read, but semantic search unavailable)
- Indexed: No indicator needed (fully ready)
- Failed: Error message with failure reason and retry option

**Failure Conditions:**
- Invalid URL or unsupported format → immediate rejection with error message
- Extraction timeout or failure (corrupt file, DRM) → `processing` → `failed`, user can retry
- Chunking/embedding failure → `ready_for_reading` → `failed` (rare, but possible), user can retry
- When failed: specific `failure_reason` shown (e.g., "Extraction failed: corrupt PDF", "Indexing failed: timeout")

---

### 3.2 Reading + Highlighting + Annotation

**User Story:** As a user, I want to read my saved content and highlight important passages with notes.

**Flow:**
1. User opens media from library
2. Reader renders content:
   - For web/EPUB: clean, distraction-free reading view (no ads, navigation chrome, or sidebars)
   - For PDF: visual rendering via PDF viewer
3. User selects text to create highlight
4. System captures: start_offset, end_offset, quote, prefix, suffix
5. User optionally selects highlight color
6. Highlight saved; immediately visible in reader
7. User can optionally add annotation to highlight
8. User can click existing highlight to view/edit/add annotation
9. User can delete highlight (cascade-deletes annotation if exists)
10. User can delete annotation (highlight remains)

**Note:** For PDFs without text layers (scanned/image-only), text selection and highlighting MUST be disabled by the reader subsystem. User can view the PDF but cannot interact with text. This is enforced by checking for empty `plain_text` field.

**Acceptance Criteria:**
- Text selection creates highlight (annotation is optional)
- Highlight colors are selectable
- User can add annotation to highlight at creation or later
- User can edit annotation body
- User can create highlight without annotation
- Highlights render correctly for all media types
- Overlapping highlights display correctly (segmented spans)
- Highlights persist across sessions
- Deleting highlight cascade-deletes annotation (if exists)
- Deleting annotation leaves highlight intact (highlight remains without annotation)

**Constraints (from domain model):**
- Offsets are 0-indexed character positions into `plain_text`
- Range is `[start_offset, end_offset)` (inclusive start, exclusive end)
- `(user_id, media_id, start_offset, end_offset)` must be unique
- Overlapping highlights allowed
- Highlights can exist without annotations
- Deleting highlight cascade-deletes annotation (if exists)
- Deleting annotation also deletes the highlight (v1 product decision; changed from earlier annotation-only delete model)
- For PDFs with empty `plain_text` (scanned/image-only), highlight creation is disallowed

**Visible States:**
- Text selected: highlight creation UI appears
- Highlight exists: colored background on text
- Edit mode: annotation editor panel open

**Failure Conditions:**
- Duplicate highlight (same exact offsets) → reject with message
- Offset mapping failure (content changed) → graceful degradation, show "highlight could not be rendered"

---

### 3.3 Managing Libraries (Default + Shared)

**User Story:** As a user, I want to organize my content into libraries and share some with others.

**Flow - Creating Library:**
1. User creates new library with name
2. Library created with user as owner/admin
3. User can add media from default library to new library
4. User can add others to library

**Flow - Joining Shared Library:**
1. User appears as `member` in LibraryUser
2. User sees library in their library list
3. User can view all media in library

**Flow - Removing Media:**
1. User removes media from a library
2. If removed from default library: also removed from all unshared libraries user owns
3. Media remains in system (no deletion)

**Acceptance Criteria:**
- Users start with one default library (auto-created on signup)
- Default library MUST NOT be deleted or shared; rename is allowed (owner/admin only)
- Users can create additional libraries
- Library owners can invite members (as `member` or `admin`)
- Admins (owner or promoted admins) can add/remove media and manage members/roles
- Removing last member (other than owner) makes library unshared
- Default library MUST NOT have members added (API-level enforcement)

**Constraints (from domain model):**
- Each user has exactly one `is_default = true` library
- Default libraries have exactly one LibraryUser row (the owner)
- Default libraries may be renamed (admin-only)
- Owner MUST always be a member with role `admin`
- Owner cannot leave library without transferring ownership or deleting it
- Library is "shared" iff LibraryUser count > 1
- Adding media to any library auto-adds to default library

**Visible States:**
- Default library: marked distinctly, no share/delete options
- Shared library: member count visible, member list accessible to admins
- Unshared library: option to invite members

**Failure Conditions:**
- Attempt to share default library → reject with message
- Attempt to delete default library → reject with message
- Attempt to leave owned library → reject (must transfer ownership or delete)

---

### 3.4 Shared Reading & Visibility

**User Story:** As a reading group member, I want to see what my group members have highlighted and annotated.

**Flow:**
1. User opens media that exists in a shared library
2. Reader loads user's own highlights
3. Reader loads visible highlights from other users (visibility rules)
4. Other users' highlights render with distinct styling (different colors, user attribution)
5. User can view annotations on others' highlights (read-only)
6. User can filter view: "My highlights only" / "All visible highlights"

**Acceptance Criteria:**
- User sees own highlights on all media
- User sees others' highlights only if they share a library containing that media
- Each highlight shows attribution (who created it)
- Others' annotations are read-only
- User can toggle between own-only and all-visible views
- Visibility updates when library membership changes

**Constraints (from domain model):**
- Visibility rule: owner OR shares library containing media with owner
- Highlights are global per (user, media); library only gates visibility
- Adding media to shared library exposes all user's highlights on that media

**Visible States:**
- Own highlight: user's selected color, editable
- Others' highlight: attributed styling, read-only
- Mixed view: clear visual distinction between own and others'

**Failure Conditions:**
- None expected in normal operation
- Deleted highlight from another user → gracefully remove from view

---

### 3.5 Global + Scoped Search

**User Story:** As a user, I want to search across all my content and find relevant passages, highlights, and notes.

**Flow:**
1. User enters search query
2. System performs hybrid search (semantic + keyword)
3. Results include: media/chunks, highlights/annotations, conversations/messages
4. Media results: all matching media (globally readable)
5. Social object results: filtered by visibility rules
6. Results ranked by relevance
7. User can click result to navigate to source

**Acceptance Criteria:**
- Single search box searches all content types
- Results grouped by type (media/chunks, highlights/annotations, conversations/messages)
- Media results show title, author, snippet with match context
- Highlight/annotation results show quote, annotation body, media reference
- Message results show content preview, conversation reference
- Conversation results show title, recent message preview
- Search respects visibility rules (user never sees others' private content)
- Results are clickable and navigate to source
- Clicking message result opens conversation and scrolls to that message
- Clicking conversation result opens conversation and scrolls to last message
- Clicking chunk result opens media and scrolls chunk location
- Clicking highlight/annotation result opens media and scrolls to highlight/annotation location

**Constraints (from domain model):**
- Media: globally readable, all matching media returned
- Social objects: visibility-scoped (owner OR shares library containing media)
- Both messages and conversations can appear as results
- Semantic search: only available for media with `processing_status = 'indexed'`
- Keyword search: available for media with `processing_status IN ('ready_for_reading', 'indexed')`
- Search must degrade gracefully: if semantic unavailable, show keyword-only results with notice

**Visible States:**
- Searching: loading indicator
- Results: grouped list with snippets
- No results: helpful empty state
- Error: error message with retry option

**Failure Conditions:**
- Search timeout → show error, allow retry
- Partial results (semantic unavailable) → show keyword results with notice

---

### 3.6 Quote-to-Chat (LLM Interaction v1)

**User Story:** As a user, I want to select a passage and ask the AI questions about it in context.

**Flow:**
1. User selects text in reader (or clicks existing highlight)
2. User chooses "Ask about this" action
3. New conversation created (or continues existing)
4. Selected quote attached as MessageContext
5. User types question
6. Message created with `role: user`
7. LLM generates response using quote + surrounding context + media metadata (title, author, date, etc.)
8. Response saved as `role: assistant` message
9. User can continue conversation with follow-up questions

**Acceptance Criteria:**
- Quote-to-chat available from text selection and highlight click
- Conversation shows the referenced quote prominently
- Clicking on the referenced quote scrolls to highlight location in media
- LLM response is contextually aware of the referenced passage
- User can ask follow-up questions in same conversation
- Conversation persists and is searchable
- User can start new conversation or continue existing one
- MessageContext links messages to referenced highlights/media

**Constraints (from domain model):**
- Conversations owned by exactly one user
- Only owner can post messages
- Message roles: `user`, `assistant`
- MessageContext types: `media`, `highlight`, `annotation`, `conversation`, `message`
- Once a user can see any message in a conversation (via shared library with referenced media), they can see all messages in that conversation, even if some messages reference non-shared media (no per-message privacy in v1)

**Visible States:**
- Chat panel: open alongside reader, replacing right panel annotations list
- Message sending: loading indicator
- Message received: assistant response rendered
- Context reference: quoted passage visible in conversation

**Failure Conditions:**
- LLM timeout → show error, allow retry
- LLM unavailable → show error message
- Referenced highlight deleted → conversation remains, context link removed, UI shows "referenced content deleted"

---

## 4. Navigation & UI Structure

### 4.1 Application Layout

**Top-level Structure:**
- Left navbar (collapsable)
- Top tabs bar (context-dependent)
- Center pane area (horizontally scrollable panes)
- Bottom footer bar (future: media player for podcasts/videos)

**Left Navbar Items (v1):**
- Libraries (opens library list)
- Documents (opens global media catalog)
- Search (opens search interface)
- Account (opens account/billing settings)

**Navbar Behavior:**
- Clicking Libraries shows user's libraries pane (default + created libraries)
- Clicking Documents shows all media in system pane (global catalog, globally readable)
- Clicking Search opens search pane with last query (or empty)
- Clicking Account opens account pane

**Pane Behavior:**
- Each media opens as two panes: content pane (left) + linked-items pane (right)
- Tabs bar shows open media (one tab per media)
- Clicking tab brings that media's panes into view (horizontal scroll)
- Closing tab closes both panes for that media
- Maximum open tabs: reasonable limit (e.g., 10) to prevent performance issues

### 4.2 Default Library Semantics (Explicit Model)

**DECISION: Default Library as Universal Personal Catalog**

The default library represents the user's complete "universe of reading"—every media item they have ever encountered in any library.

**Invariants (must be enforced):**
1. When user adds media M to ANY library, M is automatically added to default library
2. When user is added to shared library, all media in that library appear in default library
3. Removing media from default library removes it from all unshared libraries user owns (member_count == 1)
4. Removing media from default library does NOT remove it from shared libraries
5. When shared library becomes unshared (member_count → 1), all its media must be in default library
6. Default library has exactly one member (the owner) and is never shareable
7. Default library cannot be renamed, deleted, or have members added

**Cascade Deletion on Default Library Removal:**
When user removes media M from default library:
- System MUST identify all unshared libraries containing M
- System MUST remove M from each of those libraries
- System MUST display confirmation dialog listing affected libraries before removal
- User can cancel if they don't want cascade deletion

**Test Scenarios (must be explicitly covered):**
1. Add media to shared library → appears in default
2. Leave shared library → media remains in default (was added when joining)
3. Shared library transitions to personal (member_count 2→1) → all media must be in default
4. Remove from default with media in 3 personal libs and 2 shared libs → removed from 3 personal, remains in 2 shared
5. Attempt to add member to default library → rejected at API level
6. Attempt to rename default library → rejected at API level

**Product Consequence:**
- There is no "keep this only in my special collection but not in default" state
- Default library is "everything I've ever seen" minus "things I explicitly removed from all my personal contexts"
- This is complex and potentially confusing; UI must make cascade behavior extremely clear

### 4.3 Billing & Account Limits

**Tiers (v1):**

**Free Tier:**
- Up to 5 media in default library
- Unlimited library creation (but constrained by media limit)
- LLM: 0 messages per day
- All core features available

**Personal Plan ($10/month):**
- Unlimited media in default library
- Unlimited library creation
- LLM: 100 messages per day (v1 trial value, subject to adjustment based on costs)
- All core features available

**Pro Plan ($20/month):**
- Unlimited media
- Unlimited libraries
- LLM: unlimited usage (with soft rate limiting for abuse prevention)
- Priority processing for ingestion

**Note:** Specific tier limits and pricing are v1 trial values and will be adjusted based on actual costs, usage patterns, and market feedback.

**Limit Enforcement:**
- Free tier: attempting to add 6th media to default library prompts upgrade flow
- Free tier: attempting to send 11th LLM message in a day prompts upgrade flow or wait-until-tomorrow message
- Limits apply at default library level, not per individual library (since all media must be in default)

**Billing Integration:**
- Stripe for payment processing
- Subscription management in Account pane
- Grace period: 7 days after payment failure before downgrade enforcement
- Downgrade behavior: user cannot add new media until under limit; existing media remains readable

**LLM Usage Accounting:**
- Count messages sent by user (not assistant responses)
- Daily reset at midnight UTC
- Usage visible in Account pane
- V1: Simple message count, no token-level metering (may be insufficient for cost control; monitor and adjust if needed)

---

## 5. Functional Requirements by Subsystem

### 5.1 Ingestion

- System MUST accept URLs (HTTP/HTTPS) for HTML, EPUB, PDF content
- System MUST accept file uploads for EPUB and PDF formats
- Content deduplication is strict and content-based (content_hash/SHA-256 of raw bytes)
- Unique constraint on content_hash enforces strict deduplication (no two rows with identical bytes)
- canonical_url is metadata only, NOT a deduplication key (different URLs may map to same media; same URL may map to different media if content differs)
- "No duplicate documents" means "no two rows with identical bytes" (guaranteed), NOT "no conceptually-same content" (best-effort only)
- First upload of content is canonical; v1 does not support content updates or re-ingestion
- HTML extraction MUST preserve semantic structure (headings, paragraphs, lists)
- EPUB extraction MUST handle multi-chapter navigation
- PDF extraction MUST use backend processing to produce `plain_text`
- `plain_text` generation MUST be deterministic (same input → same output every time)
- Processing pipeline has two phases:
  - Phase 1 (→ `ready_for_reading`): text extraction, HTML generation
  - Phase 2 (→ `indexed`): chunking, embedding generation
- Failed processing MUST provide actionable `failure_reason` to user, indicating which phase failed
- Retry MUST clear all partial state (chunks, embeddings) before reprocessing
- All indexing (semantic and keyword) operates on canonical `plain_text`

### 5.2 Libraries & Permissions

- Default library MUST be auto-created on user registration
- Default library MUST NOT be renamed, shared, or deleted (v1 product constraint)
- Users can create additional libraries (no explicit limit in v1)
- Roles: `member` (read-only), `admin` (full management)
- Owner MUST always be a member with role `admin`, cannot be demoted
- Owner cannot leave library without transferring ownership or deleting it
- Admins can: rename library (except default), add/remove media, invite/remove members, change roles
- Members can: view media, create personal highlights/annotations
- Member removal is immediate; visibility is enforced by current shared-library intersection (ex-members' highlights immediately disappear unless another shared library contains the media)

### 5.3 Reading Interface

**Layout:**
- Navbar on left edge
- Tabs bar at top
- Footer bar at bottom
- Horizontally scrollable panes (center content area)
- Each media opens as two panes: content pane (left) + linked-items pane (right)

**Content Rendering:**
- HTML media MUST render sanitized processed HTML
- PDF media MUST render with text layer suitable for offset-based highlighting
- EPUB media MUST render with navigable chapters

**Highlight Rendering (from domain model):**
- All offsets measured against canonical `plain_text`
- Frontend MUST map offsets to DOM ranges via text node traversal
- HTML highlighting MUST be non-destructive, supporting overlapping ranges via segmented spans
- PDF highlighting MUST use overlay technique that does not modify PDF internals
- Overlapping highlights MUST segment into minimal non-overlapping spans, each annotated with all covering highlight IDs
- For PDFs with empty `plain_text` (scanned/image-only), text selection and highlighting MUST be disabled

### 5.4 Highlighting & Annotation Behavior

- Text selection MUST trigger highlight creation UI
- Highlights can exist without annotations
- Annotations can be added to highlights, edited, or omitted entirely
- Highlight list view: shows all highlights on current media (own + visible); list highlights are vertically aligned to their location in the media
- Jump to highlight: clicking in list scrolls reader to highlight location
- Edit highlight: change color
- Add/edit annotation: create or modify annotation on highlight
- Delete highlight: MUST cascade-delete annotation (if exists)
- Delete annotation: MUST leave the highlight intact
- Overlapping highlight rendering: segment into minimal spans, apply all covering highlight IDs
- Others' highlights: distinct visual treatment (attributed, read-only)
- Highlight export: not in v1 scope

### 5.5 Conversations & Messages

- Conversations created via quote-to-chat or button
- Conversation list: accessible from navigation
- Message display: chat interface
- Message creation: text input with send
- Message deletion: MUST delete associated MessageContext rows, MAY cascade-delete conversation if last message
- Context display: referenced quotes/media visible in conversation
- Conversation visibility: once a user can see any message in a conversation (via shared library with referenced media), they can see all messages in that conversation, even if some messages reference non-shared media (no per-message privacy in v1)

### 5.6 Search (Semantic + Keyword Combined)

- Single search input for all queries
- Hybrid search combining semantic similarity and keyword matching
- Result types returned: media, highlights, annotations, messages, conversations
- Media results: globally readable (all matching media returned)
- Social object results: MUST enforce visibility rules (owner OR shares library containing media)
- Media results: title, author(s), snippet
- Highlight results: quote, media title, creator name (if visible)
- Annotation results: body preview, associated quote, media title
- Message results: content preview, conversation title
- Conversation results: title, recent message preview
- Result navigation: selecting message opens conversation and scrolls to that message; selecting conversation opens conversation and scrolls to last message
- Semantic search: requires `processing_status = 'indexed'`
- Keyword search: requires `processing_status IN ('ready_for_reading', 'indexed')`
- Semantic search MUST degrade gracefully to keyword-only if media not yet indexed
- Search UI MUST indicate when results are keyword-only due to pending indexing

### 5.7 LLM Behavior (v1 Slice)

- LLM integration for quote-to-chat conversations and regular conversations
- Context window includes: selected quote, surrounding context from `plain_text`, conversation history, media metadata (title, authors)
- System prompt establishes assistant as reading companion
- Out of scope for v1:
  - Metadata repair (author detection, title correction)
  - Auto-summarization of media
- Error handling: timeout, rate limit, and model errors displayed to user with retry option

---

## 6. Quality Bars & Constraints

### Reliability Expectations

- Ingestion MUST provide actionable feedback on failure
- Retry mechanism MUST be available for all failures
- No data loss on processing failures (partial state cleaned up)
- System MUST gracefully handle LLM unavailability
- Search MUST remain available even if semantic indexing incomplete (keyword fallback)

### Security & Visibility Expectations

- CRITICAL: No visibility leakage. Users MUST NEVER see social objects they shouldn't.
- API MUST enforce visibility rules, not just UI
- Visibility rule: user sees social object iff they are owner OR currently share at least one library containing the referenced media with the owner
- Default libraries MUST NOT be shareable (API-level enforcement)
- User data isolated (no cross-tenant data access)
- Content MUST be sanitized before rendering (XSS prevention)

### Consistency Expectations

- Canonical text (`plain_text`) MUST be immutable after processing completes
- Highlights MUST never drift: offsets remain valid for lifetime of media
- Same content MUST produce same `plain_text` on re-ingestion (deterministic extraction)
- Deduplication MUST be reliable: same content not stored twice
- Real-time consistency for highlight/annotation CRUD operations (no caching that delays visibility updates)

---

## 7. Open Questions / v1 Decisions

### V1 Decisions (Must Resolve Before Implementation)

**Author Capture:**

**CRITICAL CLARIFICATION: Author Data Quality Expectations**

v1 author handling is intentionally minimal and will produce low-quality data. This is accepted technical debt.

**What happens automatically (ingestion subsystem):**
- HTML/EPUB: Authors extracted from metadata (`<meta name="author">`, `<dc:creator>`)
- Naive splitting on separators (comma, " and ", " & ")
- Exact string match deduplication (no normalization)
- This WILL create garbage entries: "NYTimes Staff", "Unknown", "–", "Smith, John and Jane Doe" (3 authors)
- PDF: no author extraction in v1 (metadata rarely reliable)

**What users can do (v1):**
- Manually create new authors via UI (for missing/incorrect metadata)
- CANNOT edit or delete authors (create-only)

**What's deferred to future metadata subsystem:**
- Author normalization ("John Smith" vs "J. Smith" are distinct in v1)
- Author disambiguation (merging, external lookups, LLM-based cleanup)
- Author editing/deletion
- Quality cleanup of ingestion-created garbage

**Consequence:** Author table will be messy; accept this for v1. Focus is on "good enough" metadata for reading, not canonical author database.

**Conversation Context Window:**
- V1: Last 10 messages + selected quote + surrounding 2000 characters from `plain_text` + media metadata
- No configurability in v1
- Hard token limit enforced by LLM provider (e.g., 100k tokens for Claude)

**Library Discovery:**
- V1: No library discovery by name or browsing
- Only via membership
- No "public libraries"

### Product Decisions (Explicit Commitments)

**DECISION: Nexus v1 is a Shared Corpus with Private Social Layer**

Nexus v1 deliberately adopts a "public corpus, private annotations" model:
- **All media is globally readable by all authenticated users.**
- **There are no private documents in v1.**
- Privacy exists only for the social layer: highlights, annotations, conversations.

**Rationale:**
- Simplifies deduplication (no need for per-user duplicate storage)
- Enables discovery of content via global documents view
- Reduces complexity of visibility rules

**Consequences:**
- Users uploading "private" PDFs will be surprised when their upload links to existing media uploaded by someone else
- Users cannot use Nexus for truly private reading material in v1
- If future versions require private documents, significant architectural changes will be needed (per-media visibility flags, rework of deduplication)

**Product Stance:**
- This is a deliberate design choice, not a limitation.
- Nexus v1 is positioned as a "shared knowledge space with personal annotations," not a "personal vault."

**DECISION: No Per-Message Privacy in Conversations**

Once a user can see any message in a conversation (via shared library containing referenced media), they can see ALL messages in that conversation, even messages referencing non-shared media.

---

**Other Consequences:**

- **Removal from libraries:** When a user removes media from all their libraries (including default), they still see their own highlights/annotations/conversations on that media (via owner rule), but the media no longer appears in their library views. Media remains accessible via the global media catalog.
- **Two-phase ingestion:** Media transitions `ready_for_reading` → `indexed`. Users can read before semantic search is ready. UI must clearly indicate indexing state.
- **Search degradation:** If searching across many media, some may be `ready_for_reading` (keyword-only) while others are `indexed` (semantic+keyword). Results must indicate which media were keyword-only.
- **No library limits:** v1 has no explicit limit on libraries per user; rely on reasonable use expectations.
