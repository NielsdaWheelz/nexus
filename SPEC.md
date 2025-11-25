# Reading-First Knowledge Management System: Production Specification

**Version**: 3.1
**Status**: Normative production specification
**Last Updated**: 2024-11-25

---

## Executive Overview

This is a production specification for a **reading-first knowledge management system** providing canonical text representation, persistent text anchoring, privacy-preserving semantic retrieval, and contextual LLM-augmented conversation over heterogeneous content (documents, episodes, videos).

### Core Pillars

1. **Canonical text**: Deterministic transformation of unstructured content (PDF, EPUB, HTML, podcasts, videos) into immutable UTF-8 byte arrays with stable offsets
2. **Persistent text anchoring**: Highlight and annotation primitives that survive content re-ingestion through deterministic remapping
3. **Privacy-preserving retrieval**: Semantic search across heterogeneous content with mandatory visibility filtering at every layer
4. **Contextual conversation**: LLM-augmented chat with retrieval-assembled context respecting visibility boundaries and token budgets
5. **Knowledge graph**: First-class links connecting documents, highlights, annotations, messages, and conversations (v1: symmetric, untyped)

### Technology Stack

- **Backend**: Python/FastAPI
- **Database**: PostgreSQL + pgvector with SQLAlchemy 2.0 ORM + Alembic migrations
- **Job Queue**: Redis + Celery
- **Frontend Web**: React (standard DOM, pdf.js)
- **Authentication**: Clerk (OIDC, JWTs)

### V1.0 Product Scope

**V1.0 Required** (core MVP):
- Document ingestion (PDF, EPUB, HTML)
- Canonical text extraction and versioning
- Highlight anchoring and remapping
- Three embedding spaces (content, thought, metadata)
- Retrieval with ACL enforcement
- LLM context assembly and chat
- Typed IDs at API boundary
- Links (untyped, symmetric)
- Celery job orchestration
- Simple document list sidebar
- Single-document reader (PDF + EPUB + Web view)
- Right-side annotation/highlight panel
- Single "chat with this document" interface

**NOT in V1.0**:
- Multi-tab document interface
- Evergreen linked-notes panel
- Global conversations (only per-document)
- Linked-object browser
- Mobile native apps (React Native)
- Podcasts/episodes/videos

**V1.1+** (future enhancements):
- Multi-tab document interface
- Evergreen linked-notes panel
- Global conversations
- Linked-object browser
- Mobile native apps (React Native)
- Podcasts/episodes, videos, typed links, advanced summaries, integrations

### Normative Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this specification are to be interpreted as described in RFC 2119.

---

## Documentation Index

This specification is split into focused subdocuments:

### Architecture & Infrastructure
- [spec/architecture.md](spec/architecture.md): Overall system design, tech stack, authentication, infrastructure choices

### Data Models & Content
- [spec/media.md](spec/media.md): Media types (documents, episodes, videos), canonical text extraction, versioning
- [spec/anchors.md](spec/anchors.md): Highlight anchoring model, anchor types (text, PDF, transcript), remapping algorithm

### Ingestion & Processing
- [spec/ingestion.md](spec/ingestion.md): Ingestion pipelines, canonicalization rules, extraction versioning
- [spec/embeddings.md](spec/embeddings.md): Chunking strategy, three embedding spaces, retrieval contracts

### Access Control & Security
- [spec/permissions.md](spec/permissions.md): Libraries, ownership model, visibility foundations
- [spec/acl.md](spec/acl.md): Formal `Visible(U, O)` function, enforcement points, threat model

### LLM & Chat
- [spec/llm_pipeline.md](spec/llm_pipeline.md): Context assembly, token budgeting, model selection, system messages

### Operations & Jobs
- [spec/jobs.md](spec/jobs.md): Celery job specifications, state machines, idempotency, retries
- [spec/frontend.md](spec/frontend.md): React web, React Native mobile, selection/anchoring, no RN-web

### API & Data Contracts
- [spec/api_contracts.md](spec/api_contracts.md): Major endpoint signatures, typed ID convention, request/response examples

### Database Schemas
- [spec/schemas/documents.md](spec/schemas/documents.md): Documents, episodes, videos, podcasts, users
- [spec/schemas/annotations.md](spec/schemas/annotations.md): Highlights, annotations, anchors
- [spec/schemas/conversations.md](spec/schemas/conversations.md): Conversations, messages, summaries
- [spec/schemas/libraries.md](spec/schemas/libraries.md): Libraries, memberships, visibility overlays
- [spec/schemas/links.md](spec/schemas/links.md): **NEW in v1**: Links (symmetric, untyped), invariants, ACL behavior
- [spec/schemas/chunks.md](spec/schemas/chunks.md): Content chunks, thought chunks, metadata chunks

---

## Key Design Decisions

### Canonical Text Over Native Formats

The system maintains a **canonical UTF-8 byte-array representation** for all text media:

- **PDFs**: Text extracted via PyMuPDF (fitz), with anchors stored in pdf.js offsets (not canonical offsets) to ensure stability
- **EPUB/HTML**: Canonical text used for both anchoring and retrieval
- **Transcripts**: Canonical transcript text with time-aligned segment metadata

This design decouples content extraction from anchoring, enabling extraction code updates without invalidating highlights.

### Hash-Based Canonical Text Model

The system uses content hashes (SHA256) instead of version integers to track canonical text changes:

- **content_hash**: SHA256 of raw blob (change detection: file re-upload)
- **anchored_content_hash** (documents): SHA256 of canonical text at anchor creation; triggers remap if changed
- **anchored_transcript_hash** (episodes/videos): SHA256 of transcript text at anchor creation; triggers remap if changed
- **pdf_file_hash** (PDFs): SHA256 of PDF binary; triggers remap only if binary changed (not extraction code)

**Canonical text is immutable**: The system stores only one canonical text per media item at any time. Historical replay of old content versions is NOT supported.

### Deterministic Remapping

Highlights survive re-ingestion via deterministic remapping algorithms:

1. **Text anchors**: Exact match search → prefix/suffix disambiguation → fuzzy search (≤10% edit distance)
2. **PDF anchors**: Search within pdf.js text layer, triggered only by file hash change
3. **Transcript anchors**: Text remapping with fallback to time-only anchor if text lost

### Visibility as Central ACL

All access control derives from a single pure function `Visible(U, O)`:

- Media visibility via library memberships or subscriptions
- User-created object visibility via ownership, explicit sharing, or public flag
- Retrieval overfetch + post-filter + defense-in-depth
- Never leak invisible object existence (404 on not-found or forbidden)

### Three Embedding Spaces

Orthogonal vector spaces for:

1. **Content** (documents, transcripts): ~400-token chunks, section metadata
2. **Thoughts** (annotations, messages, summaries): Full-text chunks, conversation context
3. **Metadata** (titles, authors, descriptions): Titles and metadata summaries

This enables boosting user's own thoughts and metadata while maintaining distinct search semantics.

### Celery for Job Orchestration

Committed architecture for background jobs (ingestion, canonicalization, chunking, embedding, remapping):

- Celery as job queue framework
- Redis as broker and result backend
- Named queues for ingestion, embedding, remap
- Concurrency limits and idempotency keys per job type
- Dead-letter queue for failed jobs

### Typed IDs at API Boundary

All external API contracts use typed string IDs:

- `doc_<uuid>` for documents
- `ep_<uuid>` for episodes
- `vid_<uuid>` for videos
- `hl_<uuid>` for highlights
- `ann_<uuid>` for annotations
- `conv_<uuid>` for conversations
- `msg_<uuid>` for messages
- `lib_<uuid>` for libraries
- `link_<uuid>` for links

Database stores raw UUIDs; transformation happens at API boundary.

### Links in v1

First-class symmetric, untyped "related" links connecting any two objects (documents, episodes, videos, highlights, annotations, messages, conversations):

- Stored once in canonical ordering to prevent duplicates
- Not separately visible; only traversed from visible objects
- Do not change visibility
- Optional "see related items" UI
- Foundation for later typed links (v2+)

### React Web for Phase 1, No Native Mobile

For **Phase 1**, only web frontend is supported:

- **Web**: Standard React DOM application, pdf.js for PDFs, standard DOM selection APIs
- **Mobile**: Delivered via responsive/mobile-friendly design (not native apps)
- **Native mobile (React Native)**: Deferred to Phase 3+ as future client

This avoids complexity in Phase 1 and focuses on robust web implementation.

---

## Out of Scope

Explicitly excluded from this specification:

- Full offline operation (optimistic UI for pending actions only)
- Multi-user collaborative editing
- Highlight version history
- First-class summary objects (summaries are conversation fields)
- Nested organizational structures (single-level libraries only)
- Workspace-level abstraction
- Anonymous access (all users must authenticate)
- Typed links in v1 (deferred to Phase 2)
- Podcast/video support in v1 (Phase 2+)
- Native mobile apps in Phase 1 (deferred to Phase 3+)

---

## Reading Guide

**For implementation of core v1**:
1. Read [spec/architecture.md](spec/architecture.md) to understand tech stack
2. Read [spec/media.md](spec/media.md) for media types and canonical text
3. Read [spec/anchors.md](spec/anchors.md) for highlighting/remapping
4. Read [spec/ingestion.md](spec/ingestion.md) for job pipelines
5. Read [spec/permissions.md](spec/permissions.md) + [spec/acl.md](spec/acl.md) for visibility
6. Read schema files under [spec/schemas/](spec/schemas/) for data models
7. Read [spec/api_contracts.md](spec/api_contracts.md) for API conventions

**For LLM context assembly**: [spec/llm_pipeline.md](spec/llm_pipeline.md)

**For job orchestration**: [spec/jobs.md](spec/jobs.md)

**For frontend implementation**: [spec/frontend.md](spec/frontend.md)

---

## Version History

- **3.1** (2024-11-25): Split monolithic spec into modular files, added links (v1), typed IDs, committed to Celery, clarified React web / React Native separation
- **3.0** (2024-11-20): Production specification baseline

