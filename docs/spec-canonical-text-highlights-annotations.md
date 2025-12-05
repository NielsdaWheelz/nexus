1. Scope
- owns: canonical plain_text definition per media kind; deterministic extraction contract; offset model; highlight+annotation lifecycle; frontend mapping contract; api surface for highlight/annotation CRUD; enforcement hooks into visibility.
- out of scope: media ingestion mechanics; library/permission logic (use visibility function only); search ranking/chunking; ui rendering details; pdf rendering internals beyond text-layer contract.

2. Responsibilities
- define canonical plain_text and normalization ensuring deterministic, stable offsets across html/epub/pdf.
- guarantee offset immutability post-ready_for_reading and mapping contract to rendered dom/pdf text layer.
- define highlight lifecycle (create/update/delete), color handling, overlap rules, uniqueness.
- define annotation lifecycle (1:1 with highlight), creation/edit/delete semantics.
- enforce visibility via shared visibility function; never store library_id on highlights/annotations.
- expose http apis for CRUD and visibility-scoped reads with explicit error codes; minimal concurrency requirements (last-write-wins).

3. Dependencies
- ingestion subsystem: produces plain_text, media.html (html/epub), pdf text layer; marks media ready_for_reading; guarantees deterministic extraction.
- libraries/permissions/visibility subsystem: authoritative `can_see_social_object(viewer, owner, media)` per published function; highlight/annotation never embed library_id.
- search subsystem: indexes highlights/annotations text fields; enforces visibility; outside ranking scope.

4. Canonical Text Specification
- definition:
  - html/epub: plain_text = deterministic linearization of ingestion-produced clean reading html in document order (text nodes only, script/style removed at ingestion). Block-level boundaries emit a single `\n` separator; inline elements concatenate directly. Html entities decoded. Non-breaking space normalized to regular space.
  - pdf: plain_text = deterministic traversal of pdf.js text layer in reading order; no pdf coordinate dependence. For scanned/image-only pdfs (empty text layer), plain_text = ''.
  - normalization: normalize line endings to `\n`; collapse runs of whitespace to a single space except within code/pre where ingestion already preserved. Strip zero-width chars. Trim leading/trailing whitespace of plain_text.
- determinism: given identical source bytes, extraction yields identical plain_text bytes. Traversal order matches frontend mapping order.
- stability: offsets are defined over plain_text only; changes to presentation html/css or viewer rendering must not alter offsets. Frontend must not re-extract; it maps to already provided media.html or pdf text layer.
- immutability: once media reaches ready_for_reading, plain_text is immutable for the lifetime of the media row. Re-ingestion of source content after this point is not supported in v1; only pre-ready retries may mutate plain_text.
- empty plain_text: if empty (e.g., scanned pdf), highlight creation is forbidden by reader and apis return 422.
- validation contract: frontend MUST verify that the concatenation produced by its traversal matches `media.plain_text` length; mismatches are bugs to be logged/alerted and block highlight creation until resolved.

5. Offset Model
- offsets are 0-indexed character positions into plain_text; start inclusive, end exclusive `[start_offset, end_offset)`.
- validity: 0 ≤ start_offset < end_offset ≤ len(plain_text). Zero-length ranges forbidden.
- stored fields: start_offset, end_offset, quote (exact slice), prefix (up to 30 chars before), suffix (up to 30 chars after).
- uniqueness: (user_id, media_id, start_offset, end_offset) unique; duplicate ranges for same user/media rejected (409) on create and on update.
- overlap: overlapping ranges allowed; segmentation handled in rendering contract.
- drift handling: offsets should not drift post-ready_for_reading. Server recomputes quote/prefix/suffix from plain_text on create and update and returns canonical slices; if client-provided values differ, server ignores client versions and logs. If offsets are out of bounds, reject with 400. If plain_text empty, reject with 422. V1 does not perform anchor recovery; unresolved highlights remain unresolved until edited or deleted.
- prohibited ranges: negative offsets, end beyond length, start==end, or start>end; spans across missing plain_text (empty string) forbidden.

6. Rendering Contract (Frontend)
- render source: must render the ingestion-produced display HTML (not live-fetched or re-run extraction) for html/epub; for pdf use the pdf.js text layer produced from the same bytes/algorithm as ingestion.
- dom traversal: frontend MUST use the same deterministic text-node traversal as ingestion: TreeWalker over text nodes in document order on the processed display DOM, concatenating node.textContent exactly as emitted (no additional whitespace collapsing beyond DOM behavior), with `\n` separators only where ingestion inserted them. The concatenation must equal media.plain_text byte-for-byte.
- mapping self-check: prior to applying highlights, frontend SHOULD compute the traversal length (and optionally checksum) and compare to `media.plain_text`; on mismatch, surface an error and skip highlight rendering/creation (treat as bug). This check applies on first render and whenever documentHTML changes.
- dom mutation pattern: perform segmentation on a detached DOM/container, then swap into the live container to avoid layout thrash; do not rely on innerText/outerHTML re-extraction.
- offset → dom range: resolve start/end into text nodes; split nodes at boundaries.
- overlapping segmentation: compute minimal non-overlapping spans; each span carries the set of covering highlight_ids for styling/interaction.
- html/epub wrapping: wrap spans in `<mark data-highlight-ids="...">` (or equivalent) without altering text content; preserve selection offsets; avoid nested marks by flattening segmented spans; include all covering highlight ids in data attributes (and an optional primary id for hover/selection grouping).
- pdf.js text-layer contract: ingestion and frontend derive plain_text by walking the pdf.js text layer with the same item order and concatenation rules. Frontend operates on text layer spans; overlay rectangles anchored to text layer positions; never use pdf coordinates directly; rerender on text-layer reflow/scale events.
- failure modes: if mapping fails (invalid offsets, missing nodes, empty text layer, length/checksum mismatch), render highlight as unresolved pill in sidebar/list and block creation; do not guess offsets against live dom.

7. Highlight Specification
- creation: allowed only when media.processing_status ∈ {ready_for_reading, indexed} and plain_text non-empty. Validate offsets against plain_text length; compute quote/prefix/suffix from plain_text and return canonical values (ignore mismatching client-provided values). Color optional; default system color if absent.
- update: offsets mutable. Allowed updates: start_offset, end_offset (with full revalidation and recomputation of quote/prefix/suffix), color, client_metadata (if present), visibility toggle for own display-only flags. Media_id and user_id are immutable. Enforce uniqueness on the new (user_id, media_id, start_offset, end_offset); reject conflicts with 409. Update is owner-only; preserves created_at.
- delete: owner-only hard delete; cascade deletes annotation (if exists). Idempotent: deleting missing highlight returns 204.
- visibility: never stores library_id. Read visibility via `can_see_social_object(viewer, owner, media)`; creation/update/delete only by owner.

8. Annotation Specification
- relation: 1:1 with highlight (highlight may have 0 or 1 annotation). Annotation cannot exist without highlight.
- creation: owner-only; allowed only if highlight exists and not deleted. Body required (non-empty string). Offsets inherited; not stored on annotation.
- editing: owner-only; edit body; highlight offsets/color unaffected.
- deletion: owner-only; deletes annotation only; highlight remains. Deleting highlight cascade-deletes annotation. (Model: highlight is primary, annotation is optional.)
- visibility: derived from parent highlight via same visibility function.

9. APIs (HTTP)
- common: path prefix `/api/v1/...`. All requests authenticate user; enforce owner-only for mutations; visibility checks for reads using visibility function. All responses include highlight/annotation payloads with ids, timestamps, owner_user_id, media_id. Machine-readable error codes accompany HTTP status.

- POST `/api/v1/media/{media_id}/highlights`
  - request: `{ start_offset, end_offset, quote?, prefix?, suffix?, color? }`
  - validate offsets; recompute quote/prefix/suffix server-side and return canonical slices.
  - responses: 201 with highlight; errors: INVALID_OFFSETS (400), UNAUTHORIZED (401), FORBIDDEN (403), MEDIA_NOT_FOUND (404), DUPLICATE_HIGHLIGHT_SPAN (409), EMPTY_PLAIN_TEXT (422).
  - concurrency: uniqueness constraint on (user_id, media_id, start, end) handles duplicate attempts; no idempotency-key required in v1.

- PATCH `/api/v1/highlights/{highlight_id}`
  - allowed fields: `start_offset`, `end_offset`, `color`, `client_metadata?`
  - behavior: validate new offsets; enforce uniqueness on (user_id, media_id, start, end); recompute quote/prefix/suffix from plain_text and return canonical values.
  - responses: 200 with updated highlight; errors: INVALID_OFFSETS (400), UNAUTHORIZED (401), FORBIDDEN (403), HIGHLIGHT_NOT_FOUND (404), DUPLICATE_HIGHLIGHT_SPAN (409), EMPTY_PLAIN_TEXT (422 if media has no text).

- DELETE `/api/v1/highlights/{highlight_id}`
  - responses: 204; errors: UNAUTHORIZED (401), FORBIDDEN (403), HIGHLIGHT_NOT_FOUND (404). Cascade deletes annotation.
  - idempotent: repeat delete returns 204.

- POST `/api/v1/highlights/{highlight_id}/annotations`
  - request: `{ body }`
  - responses: 201 with annotation; errors: INVALID_BODY (400), UNAUTHORIZED (401), FORBIDDEN (403), HIGHLIGHT_NOT_FOUND (404), ANNOTATION_ALREADY_EXISTS (409).

- PATCH `/api/v1/annotations/{annotation_id}`
  - request: `{ body }`
  - responses: 200; errors: INVALID_BODY (400), UNAUTHORIZED (401), FORBIDDEN (403), ANNOTATION_NOT_FOUND (404).

- DELETE `/api/v1/annotations/{annotation_id}`
  - responses: 204; errors: UNAUTHORIZED (401), FORBIDDEN (403), ANNOTATION_NOT_FOUND (404). Highlight remains.
  - idempotent: repeat delete returns 204.

- GET `/api/v1/media/{media_id}/highlights`
  - params: `visibility_scope` (default `visible_to_viewer`, optional `mine_only`), pagination cursor.
  - responses: 200 list of highlights visible to viewer per visibility function; includes annotation presence flag and annotation payload if visible.
  - errors: UNAUTHORIZED (401); MEDIA_NOT_FOUND (404).

- GET `/api/v1/highlights/{highlight_id}/annotation`
  - responses: 200 annotation if exists and visible; 204 if none; errors: UNAUTHORIZED (401), FORBIDDEN (403), HIGHLIGHT_NOT_FOUND (404).

- concurrency: last-write-wins for mutable fields (start_offset, end_offset, color, annotation body). No optimistic concurrency headers in v1.
- combined create: creating a highlight with annotation is two calls (create highlight, then create annotation) in v1; no batch endpoint provided.

10. Invariants
- plain_text is canonical, deterministic, and immutable after ready_for_reading.
- all offsets index into plain_text only; backend stores no dom offsets.
- (user_id, media_id, start_offset, end_offset) unique; overlapping allowed; duplicates forbidden (enforced on create and update).
- highlights & annotations never store library_id.
- visibility derived only via shared library rule: viewer sees object iff viewer==owner or ∃ library containing media with both viewer and owner members.
- highlight deletion cascade-deletes annotation; annotation deletion does not delete highlight.
- annotation optional; highlight can exist without annotation.
- offsets may be updated in place; updates must validate against plain_text and uniqueness and recompute quote/prefix/suffix.
- no highlights allowed when plain_text empty.
- search uses same visibility filter; must not surface invisible social objects.
- pdf highlights map to pdf.js text layer, never pdf coordinates.

11. State Machines
- highlight:
  - `created` → `deleted` (hard delete). No other states; offsets immutable; color mutable.
- annotation:
  - `created` → `deleted` (hard delete). Exists only while parent highlight exists.

12. Error Handling
- invalid offsets (start>=end, out of bounds): 400 INVALID_OFFSETS.
- empty plain_text: 422 EMPTY_PLAIN_TEXT.
- duplicate range for user/media: 409 DUPLICATE_HIGHLIGHT_SPAN.
- unauthorized read/write: 401 UNAUTHORIZED / 403 FORBIDDEN.
- not found (hidden or deleted): 404 HIGHLIGHT_NOT_FOUND / ANNOTATION_NOT_FOUND / MEDIA_NOT_FOUND.
- unrenderable (client): render placeholder; server still returns stored data.

13. Performance & Limits
- indexing: btree on (user_id, media_id, start_offset, end_offset) for uniqueness and range queries; index on (media_id) for visible fetch.
- pagination required for fetch highlights; default page size bounded (e.g., 100); caller-provided cursor.
- retrieval scale: must handle thousands of highlights per media; queries must remain <100ms p95 with indexes.
- payload size: store quote/prefix/suffix as small text; no explicit max span length specified here—ensure db column lengths accommodate long selections; reject excessively large bodies via validation consistent with db limits.
- future media kinds: transcripts reuse the canonical plain_text model (plain_text = transcript text; offsets identical to HTML behavior; any timestamps live in a separate mapping outside this spec).

14. Test Matrix
- offset correctness: create highlights with boundary offsets; verify stored quote/prefix/suffix match plain_text slices; reject out-of-range.
- mapping correctness: verify frontend traversal reproduces plain_text byte-for-byte for html/epub and pdf.js text layer.
- overlapping segmentation: render overlapping highlights and verify minimal span segmentation and mark wrapping.
- visibility: ensure viewer sees own highlights always; sees others only when shared library exists; verify removal of shared library hides others.
- api: CRUD endpoints success/error codes, uniqueness conflicts.
- concurrency: parallel creates on same range yield single row and 409 on loser; last-write-wins for mutable fields.
- deletion propagation: delete highlight cascades annotation; delete annotation leaves highlight; ensure fetch reflects.
- pdf mapping: ensure offsets map via pdf.js text layer; empty text layer forbids creation.

15. Open Questions
- none.

