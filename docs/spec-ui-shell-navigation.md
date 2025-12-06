# Nexus Subsystem Spec: UI Shell & Navigation

## 1. scope
- Define the application shell, navigation model, pane/tab behavior, and UI-state contracts for Nexus v1 (desktop-first, responsive web).
- Cover what screens/panes exist, how they open/focus/close, tab rules for media, allowed backend calls per pane, required loading/error/empty states, and observability hooks.
- Stay consistent with `domain-model.md`, `prd.md`, `spec-auth-accounts.md`, `spec-libraries-permissions-visibility.md`, `spec-canonical-text-highlights-annotations.md`, `spec-chunking-search-index.md`, `spec-conversations-llm.md`, and `spec-billing-subscriptions-usage.md`. Do not redefine entities or visibility rules.

## 2. dependencies
- Auth/accounts: current user and session (`/auth/me`).
- Libraries/permissions/visibility: library membership, shared-library visibility rule for social objects.
- Canonical text/highlights/annotations: highlight rendering and visibility.
- Chunking/search/index: search API behavior and result types.
- Conversations/LLM: quote-to-chat flows, conversation/message visibility.
- Billing/subscriptions/usage: billing overview surfacing in Account pane; tier limits influence UX affordances (e.g., media add failures).
- Ingestion: media processing status, kind, plain_text availability to gate highlighting and viewing states.

## 3. responsibilities
### must do
- Provide the shell layout: collapsible left navbar, top tabsbar (every open pane is a tab), horizontally scrollable center panes with default widths, reserved footer bar (minimal in v1), and consistent focus model.
- Manage pane lifecycle: open/focus/close panes; enforce singleton panes (Libraries, Documents, Search, Account, Conversations) as one tab each; pair media content + linked-items panes per media tab; pair conversation thread + context panes per conversation tab; horizontal scroll for overflow.
- Enforce navigation rules: clicking navbar opens or focuses its singleton tab; opening media opens/focuses its media tab; opening conversation opens/focuses its conversation tab; closing a tab closes the associated pane pair.
- Define right-pane behavior: linked-items list (highlights/annotations/messages); clicking/creating a message opens/jumps to a conversation tab for full chat.
- Specify allowed backend calls per pane (conceptual: “libraries API”, “media API”, “search API”, etc.) and respect visibility constraints (global media; social objects visibility-scoped).
- Define required loading/error/empty states per pane and behavior on fatal errors (e.g., close pane + toast on 404).
- Cap open media tabs and heavy renders; require list virtualization for large result sets.
- Emit navigation observability events/metrics.

### must not do
- Must not create new domain rules, visibility semantics, or API shapes beyond referenced specs.
- Must not surface social objects the viewer is not allowed to see; never rely on client-side filtering only.
- Must not spawn duplicate singleton panes or duplicate media tabs.
- Must not keep background heavy viewers active beyond limits defined here.

## 4. pane & navigation model
### layout
- Regions: left navbar (collapsible), top tabsbar (all open tabs: singletons, media tabs, conversation tabs), center pane area (horizontally scrollable panes), reserved footer bar (for future media players; v1 shows placeholder only when active media player exists).
- Panes have a fixed default width; multiple panes can exceed viewport width; center area horizontally scrolls.
- Focus order: the most recently focused pane scrolls into view; keyboard focus tracks pane content.

### pane types (v1)
- Libraries pane (singleton):
  - Purpose: list libraries the user belongs to (default + others), actions to open a library detail, create library.
  - Data/API: libraries API list/create; must not call media search.
  - Visibility: only libraries where viewer is a member (per libraries spec).
  - States: loading list; empty (no libraries beyond default); error (list failed).
- Library Detail pane (one per open library):
  - Purpose: list media in selected library; actions: open media; remove media (if admin/owner); optional add from Documents.
  - Data/API: library-media list/removal; add via library-media add; must respect role checks.
  - Visibility: only if viewer is member; media list includes all media in that library (media are globally readable).
  - States: loading; empty (no media); permission error → close pane + toast; library not found → close pane + toast.
- Documents pane (singleton):
  - Purpose: global media catalog; action: add media to my library (default or chosen) if limits permit.
  - Data/API: global media list/search (media API); add-to-library calls library-media add and media limit enforcement.
  - Visibility: global (media are public); never surfaces other users’ social objects.
  - States: loading; empty (no media found); add failure surfaces billing/limit errors inline.
- Media Content pane (paired with linked-items for each media tab):
  - Purpose: render single media (html/epub/pdf).
  - Data/API: media fetch by id; uses `processing_status`, kind, plain_text presence to gate interactions (respect scanned PDF no-highlight rule).
  - Visibility: media always readable.
  - States: loading; processing states per ingestion/PRD; error (not found/forbidden) → close tab + toast; view-only state for empty plain_text PDFs.
- Linked-Items pane (paired, right side of media tab):
  - Behavior: linked-items list containing highlights, annotations, and messages aligned to the media; no inline mini-thread expansion. Clicking a message (or “ask about this”) opens/focuses the corresponding conversation tab for full chat; the list stays as-is.
  - Data/API: highlights/annotations/messages list for media (visibility-scoped); message rows link to conversation tabs; sending a message is done in the conversation tab (not inside linked-items).
  - Visibility: only social objects allowed by shared-library rule; show attribution for others.
  - Interaction rules:
    - Default on open: linked-items list.
    - “Ask about this” from a selection or existing highlight: create/focus conversation; open/focus its conversation tab; linked-items remains list-only.
    - Clicking a message row: open/focus its conversation tab; linked-items remains list-only.
    - Opening a conversation result (search) or context link: open/focus conversation tab; linked-items stays in list mode.
  - States: loading; empty (no highlights/messages visible); permission error → show inline error; media not ready (plain_text empty) → disable highlight-related UI.
- Conversations pane (singleton tab):
  - Purpose: list conversations visible to the user; actions: open conversation tab.
  - Data/API: conversations list API.
  - Visibility: includes owned conversations and shared-readable per conversations spec.
  - States: loading; empty (no conversations); error (list failed or permission).
- Conversation tab (paired panes):
  - Left pane: conversation thread (messages) with send box; uses conversations/messages APIs; owner-only send enforced by backend.
  - Right pane: message context items for the active thread (media/highlight/annotation references), including per-message chips that link back to media; clicking a context item opens/focuses the associated media tab and scrolls to the linked item.
  - Visibility: conversation visibility per conversations spec; contexts respect media visibility (media is public) and social object visibility.
  - States: loading; empty (no messages yet); permission error → close tab + toast; conversation not found → close tab + toast.
- Search pane (singleton):
  - Purpose: run searches; show grouped results: media, highlights/annotations, messages, conversations.
  - Data/API: search API (global or scoped); must pass viewer context for visibility filtering.
  - Visibility: media global; social objects only if visible per rules.
  - States: idle; loading; results (paged); empty (no matches); error (show inline and allow retry).
- Account pane (singleton):
  - Purpose: user profile stub + embedded billing overview.
  - Data/API: `/auth/me`; billing overview endpoint.
  - States: loading; error (auth expired → prompt re-login; billing failure → inline error with retry).

### tabs behavior (all panes)
- Tabsbar shows every open tab: singletons (one tab each, non-duplicable), media tabs (paired content+linked-items), conversation tabs (paired thread+context).
- Tab limit: max 10 total tabs open concurrently (media + conversation + any open singletons count; singletons remain one each). Opening a new tab at limit blocks with “close a tab to open another.”
  - Opening an already-open resource focuses its tab.
  - Closing a tab closes both associated panes; focus falls back to the most recent remaining tab.
- Tabsbar overflow: horizontal scroll; tabs retain order of most-recent-open unless user reorders (reorder optional; v1 fixed order by open time).

### navbar behavior (singletons)
- Navbar items (v1): Libraries, Documents, Search, Conversations, Account.
- Clicking an item opens or focuses its singleton pane (and its tab); never creates duplicates.
- Navbar collapse/expand does not affect pane state.
- If pane load fails with 401/403/404, close pane and surface toast; navbar remains usable.

### center pane stacking & scroll
- Panes (singletons + any tab pair) share a horizontal track; order is stable by open time with active pane pair scrolled into view on focus.
- All panes correspond to tabs; singletons appear in tabsbar once opened.
- Close control exists per pane (except required right-side pair members).

- Open library → open media → view highlights/messages → start chat:
  - Navbar Libraries → Libraries pane loads.
  - Select library → opens Library Detail pane.
  - Select media → opens/focuses media tab (content + linked-items in linked-items list mode).
  - Select text/highlight → create highlight (if plain_text present) then “Ask about this” → creates a user message and opens/focuses the corresponding conversation tab; linked-items remains a list.
- Open documents pane → add media to library → open media:
  - Navbar Documents → Documents pane.
  - Browse/search global media → choose “Add to my library” (targets default or selected library; enforces billing/media limits).
  - Open media → media tab opens/focuses; linked-items starts in linked-items list mode.
- Run search → open result (media / highlight / message / conversation):
  - Navbar Search → Search pane.
  - Enter query → search API.
  - Click media result → opens/focuses media tab.
  - Click highlight/annotation result → opens/focuses media tab and scrolls/filters linked-items list to that highlight; keeps list mode.
  - Click message result → opens/focuses its conversation tab (and associated media tab if needed for context).
  - Click conversation result → opens/focuses conversation tab; right pane lists context items; clicking a context opens its media tab.
- Conversations pane → open conversation tab:
  - Navbar Conversations → Conversations pane (tab).
  - Select conversation → opens/focuses conversation tab (thread left, contexts right).
  - Selecting a context item in the right pane opens/focuses its media tab and scrolls to the linked item.

- Tabs are unique per resource: one per media id, one per conversation id, one per singleton type.
- Each media tab always renders exactly two panes: left content, right linked-items; right pane remains a list (no inline chat).
- Each conversation tab renders exactly two panes: left thread, right context items; send is owner-only (backend enforced); contexts stay visibility-safe.
- Linked-items list for a media shows highlights, annotations, and messages the viewer can see; message rows expand inline mini conversations; no invisible owners are shown.
- Visibility guard: linked-items and chat views only render social objects allowed by shared-library rule; do not show unknown owners or partial conversations.
- Highlights UI disabled when media.plain_text is empty (scanned PDFs) or media not ready_for_reading.
- Pane state isolation: errors in one pane do not corrupt others; closing a tab never closes other tabs beyond its pair.
- Navigation actions are idempotent (re-clicking navbar or opening already-open media/conversation just focuses).

## 7. error handling + loading/empty states
- Common patterns:
  - Loading: skeleton or spinner within pane body.
  - Empty: descriptive message + primary action if applicable (create library, add media, new search).
  - Error: inline error banner + retry; fatal (404/403) → close pane/tab and toast.
- Pane specifics:
  - Libraries pane: load error stays in-pane with retry; if 401 → prompt re-login.
  - Library detail: 404/permission → close pane + toast; removal/add failures show inline errors.
  - Documents: add-to-library failures surface billing/media-limit codes; list errors inline.
  - Media content: 404/permission → close tab + toast; processing states map to PRD indicators; LLM quota errors shown only in chat mode.
  - Linked-items: visibility/permission errors show inline; conversation not found → return to linked-items list with toast; message expansion failures collapse the mini thread and show inline error.
  - Conversation tab: 404/permission → close tab + toast; send failures surface inline (quota, forbidden).
  - Conversations pane: load error inline with retry.
  - Search: network/error shows inline; unsupported result type group shows static “not supported in v1”.
  - Account: auth expired → prompt re-login; billing overview failure → inline error with retry.

## 8. performance & limits
- Tab cap: 10 total open tabs (media + conversation + singletons).
- Requirements (not prescriptive strategies):
  - Avoid keeping excessive heavy viewers alive simultaneously; memory/cpu should scale reasonably with visible tabs.
  - Avoid background polling storms; network usage should scale with visible/active tabs.
  - Use list virtualization for large lists (libraries, library media, documents, search results, linked-items, conversations, messages, contexts).
  - Paginate all list/data fetches per underlying APIs; no unbounded fetches.
  - Debounce/serialize high-frequency actions (e.g., search input) to prevent request floods.

## 9. observability
- Events (minimal v1):
  - navbar_click (item), pane_open (type/id), pane_close (type/id, reason), pane_focus (type/id).
  - tab_open/tab_close/tab_focus (id, type, source).
  - search_submit (query_length, scope), search_result_open (type, target_id, media_id?).
  - quote_to_chat_start (media_id, highlight_id), chat_send (conversation_id, media_id, success/error_code).
  - add_to_library_action (media_id, library_id, outcome, error_code).
- Metrics (minimal v1):
  - open_tabs_avg/max_p99.
  - pane_open_count by type; pane_error_count by type/error_code.
  - search_latency_p50/p95; search_error_rate.
  - chat_send_error_rate (by error_code).
  - add_to_library_failure_rate (by error_code).
- Traces: basic nav flows (search → open media → chat) with spans for API calls; tag with user_id where allowed.

## 10. test matrix (integration/e2e scenarios)
- Navbar singletons: open/focus/close behavior; no duplicates; singletons appear as tabs when opened.
- Tab lifecycle: open media from each source; open conversation from Conversations pane and from linked-items; focus existing tabs; hit cap (10) → blocked with toast; close tab removes panes.
- Media rendering states: processing → ready_for_reading indicators; scanned PDF disables highlights; 404 closes tab.
- Linked-items list: shows highlights/annotations/messages; quote-to-chat creates message and opens conversation tab; clicking message opens conversation tab; permission denied hides others’ items; shared library shows others with attribution.
- Search flows: media result opens tab; highlight result focuses linked-items; message result opens conversation tab; conversation result opens conversation tab and context links open media tab.
- Library detail permissions: member vs admin remove/add; non-member 403 closes pane.
- Documents add-to-library: success updates library; over media limit shows billing error; still can open media globally.
- Conversations pane: list loads; open conversation tab; context item open → media tab focused; permission/404 closes tab.
- Account pane: auth expiry prompts re-login; billing overview failure handled inline.
- Observability: events emitted for pane/tab open/close, search submit, tab cap block, quote-to-chat start/send, add-to-library outcome.

## 11. open questions
- Should background media tabs prefetch linked-items on open instead of on first focus? Current default: fetch on first focus to save bandwidth.
- Do we allow singletons to be closed from tabsbar, or should they be pinned once opened? Current default: closable.

## 12. future extensions
- Footer media player for podcasts/videos with mini-controls and persistent playback across tabs.
- Link-graph/related-items visualization pane.
- Tab grouping/pinning and session restore.
- Unified notification center for shared activity.
- Mobile-optimized shell adjustments (stacked panes, bottom nav).

