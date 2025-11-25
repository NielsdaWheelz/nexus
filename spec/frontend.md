# Frontend Architecture

## 1. Web Frontend (React DOM) — Phase 1 Only

### 1.1 Stack

- **Framework**: React 18+
- **Rendering**: DOM (not Canvas, not WebGL)
- **PDF**: pdf.js for client-side rendering
- **Text selection**: Standard DOM `Selection` API
- **State management**: React Query (TanStack Query) for server state, Zustand for UI/local state
- **HTTP client**: Generated from OpenAPI schema or hand-written
- **Auth**: Clerk React SDK

**Phase 1 scope**: Web-only frontend. Mobile support via responsive/mobile-friendly design. Native apps (React Native) deferred to Phase 3+.

### 1.2 Rendering Engines

#### PDFs

- **Library**: pdf.js (Mozilla)
- **Approach**: Client-side rendering via `<canvas>`
- **Text layer**: Extracted via pdf.js, used for highlight positioning
- **Selection**: Text selection in pdf.js viewer creates anchors via text layer offsets
- **Highlight rendering**: Canvas overlays for colored highlights

#### EPUB/HTML

- **Rendering**: Standard HTML + CSS
- **Text extraction**: `textContent` of document for canonicalization
- **Selection**: Standard DOM `Selection` API for highlight creation
- **Highlight rendering**: DOM `<span>` wrapping with background color (NOT canvas overlays)

#### Transcripts

- **Not in Phase 1** (deferred to Phase 2+)

### 1.3 Selection & Anchoring

**Text selection flow**:

1. User selects text in reader (mouse/touch)
2. Frontend captures `Selection` object (for EPUB/HTML) or pdf.js text layer (for PDF)
3. Compute byte offsets:
   - EPUB/HTML: UTF-8 byte offsets in canonical text
   - PDF: Character offsets in pdf.js text layer
4. Compute context (prefix/suffix)
5. Create highlight object via API
6. Render inline

**Byte offset computation**:

```typescript
function getByteOffset(text: string, charOffset: number): number {
  // Convert character offset to byte offset in UTF-8
  return new TextEncoder().encode(text.substring(0, charOffset)).length;
}
```

### 1.4 Highlight Rendering

**For HTML/EPUB (DOM Span Wrapping)**:

```typescript
function renderHighlight(highlight, sourceText) {
  // Extract the highlighted text from canonical_text
  const start = highlight.text_start;
  const end = highlight.text_end;
  const quote = sourceText.substring(start, end);

  // Find text in DOM and wrap with <span class="highlight">
  // (Complex: requires text node traversal, handling line breaks, etc.)
  // Result: highlighted text visually styled with background color
}
```

**For PDFs (Canvas Overlays)**:

```typescript
function renderPDFHighlight(highlight) {
  // PDF: use pdf.js page and offset to position overlay
  const pageIndex = highlight.pdf_page_number - 1;
  const offsetInPage = highlight.pdf_char_offset;

  // Render canvas overlay at computed (x, y) position
}
```

**Rationale for DOM spans over canvas**: DOM spans are simpler, more robust, and more maintainable. Canvas overlays for HTML/EPUB break on resize, font changes, and dynamic layout shifts.

---

## 2. Mobile Frontend (Future — Phase 3+)

Mobile frontend via React Native is deferred to Phase 3+:

- Not part of Phase 1 specification
- Mobile support in Phase 1 via responsive web design
- Native apps (iOS/Android) planned for Phase 3+

---

## 4. Selection & Anchoring Invariants

All selection/anchoring logic MUST satisfy these invariants regardless of frontend:

**INV-1**: Byte offsets MUST be computed in UTF-8 encoding. All text is normalized to NFC before byte offset computation.

**INV-2**: For PDFs, offsets refer to pdf.js text layer extraction, not canonical text. This ensures stability across extraction code updates.

**INV-3**: For text media, offsets refer to canonical text at the time of highlight creation. These offsets may become stale if canonical text changes (remap triggered).

**INV-4**: Context (prefix/suffix) MUST be extracted from the same text source as the quote. Mismatches break remap.

---

## 2.1 Markdown Rendering Ruleset

All markdown content is processed through a standardized pipeline:

### 2.1.1 Markdown Subset

The system supports a CommonMark subset with the following features:

**Allowed**:

- Headings: `# Heading 1` through `### Heading 3`
- **Bold**: `**text**` or `__text__`
- *Italic*: `*text*` or `_text_`
- Inline code: `` `code` ``
- Fenced code blocks: ` ``` ` with language identifier
- Lists: Unordered (`-`, `*`, `+`) and ordered (`1.`, `2.`, etc.)
- Blockquotes: `> quoted text`
- Links: `[text](url)`
- Line breaks: Explicit line breaks

**NOT allowed**:

- Images: `![alt](url)` – forbidden
- Tables: Markdown tables – forbidden
- HTML blocks: Raw `<html>` – forbidden
- Raw HTML inline: `<div>` – forbidden
- Footnotes, definitions, strikethrough

### 2.1.2 Processing Pipeline

```
Raw markdown (stored) → Parse (CommonMark) → Render → HTML
                                                    ↓
                                          Sanitize HTML (Bleach)
                                                    ↓
                                          Serve to frontend
```

**Implementation**:

```python
import markdown
import bleach

def render_markdown(raw_md: str) -> str:
    """Render markdown with sanitization."""
    # Parse markdown to HTML
    html = markdown.markdown(
        raw_md,
        extensions=['extra'],  # Common tables, strikethrough, etc.
        output_format='html'
    )

    # Sanitize output
    allowed_tags = ['p', 'h1', 'h2', 'h3', 'em', 'strong', 'code', 'pre',
                    'ul', 'ol', 'li', 'blockquote', 'a', 'br']
    allowed_attrs = {'a': ['href']}

    clean_html = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    return clean_html
```

**Rationale**:

- Store raw markdown for editability and future tool compatibility
- Render to HTML for consistent display
- Sanitize to prevent XSS in annotations and messages

### 2.1.3 Example

**Input (raw markdown)**:

```markdown
# My Title

This is **bold** and *italic* text.

```python
def hello():
    print("Hello world")
```

[Link](https://example.com)
```

**Output (sanitized HTML)**:

```html
<h1>My Title</h1>
<p>This is <strong>bold</strong> and <em>italic</em> text.</p>
<pre><code class="language-python">def hello():
    print("Hello world")
</code></pre>
<p><a href="https://example.com">Link</a></p>
```

---

## 3. State Management Architecture

### 3.1 Stack

**React Query (TanStack Query)** for server state:

All data fetched from the backend MUST be managed via React Query:
- Documents, episodes, videos
- Highlights, annotations
- Conversations, messages
- Search results
- Chunks (for retrieval context)

**Zustand** for UI/local state:

Presentation-only state managed via Zustand:
- Current document ID
- Selected highlight ID
- Sidebar visibility toggle
- Multi-pane layout state
- Scroll position
- Selection ephemeral state (being constructed, not yet committed)

### 3.2 Prohibited Patterns

- **Redux**: Not used in Phase 1 (deferred to Phase 2+ if needed)
- **Custom fetch wrappers**: All server data must flow through React Query, not custom hooks
- **Global Zustand store for server state**: Zustand MUST NOT contain server-synchronized data; that's React Query's job

### 3.3 Clarification

- **React Query handles**: Caching, syncing with backend, invalidation, polling, request deduplication
- **Zustand handles**: Presentation, transient UI state, no server synchronization

### 3.4 Example Architecture

```typescript
// Server state via React Query
const { data: documents, isLoading } = useQuery(['documents'], fetchDocuments);
const { data: highlights } = useQuery(['highlights', docId], () => fetchHighlights(docId));

// UI state via Zustand
const { selectedDocId, setSel ectedDocId } = useUIStore();
const { sidebarOpen, toggleSidebar } = useUIStore();

// React components
function DocumentReader() {
  const { data: document } = useQuery(['document', selectedDocId], ...);
  const { data: highlights } = useQuery(['highlights', selectedDocId], ...);
  const { toggleSidebar } = useUIStore();

  return (
    <PDFViewer
      pdf={document.blob}
      highlights={highlights}
      onSelect={handleSelection}
    />
  );
}
```

---

## 4. Client-Side Caching & Invalidation (React Query)

This section defines client behavior for caching and keeping data synchronized with the backend.

### 4.1 React Query Configuration Defaults

**Global defaults**:

```typescript
import { QueryClient } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,        // 5 minutes
      cacheTime: 30 * 60 * 1000,       // 30 minutes
      retry: 2,
      retryDelay: (attemptIndex) => 1000 * (2 ** attemptIndex),
      refetchOnWindowFocus: true,
      refetchOnReconnect: 'stale',
      refetchOnMount: 'stale'
    },
    mutations: {
      retry: 1,
      retryDelay: 1000
    }
  }
})
```

### 4.2 Cache Timing by Data Type

| Data Type | `staleTime` | `cacheTime` | Notes |
|-----------|------------|------------|-------|
| Documents (list) | 5 min | 30 min | Fairly stable, user rarely creates many |
| Document (detail) | 10 min | 60 min | Stable while reading |
| Highlights | 2 min | 15 min | Frequently modified (highlight creation) |
| Annotations | 2 min | 15 min | Frequently modified (typing notes) |
| Conversations | 1 min | 10 min | Real-time-ish, refresh often |
| Messages | 30 sec | 5 min | Very fresh for chat experience |
| Search results | 1 min | 10 min | Query-specific, invalidate on query change |
| Chunks (retrieval) | 5 min | 30 min | Static until embedding changes |

### 4.3 Mutation Invalidation Rules

**On highlight creation/update**:

```typescript
mutationFn: createHighlight,
onSuccess: (newHighlight) => {
  queryClient.invalidateQueries(['highlights', docId])
  queryClient.setQueryData(['highlight', newHighlight.id], newHighlight)
}
```

**On annotation creation/update**:

```typescript
mutationFn: createAnnotation,
onSuccess: (newAnnotation) => {
  queryClient.invalidateQueries(['annotations', docId])
  queryClient.setQueryData(['annotation', newAnnotation.id], newAnnotation)
}
```

**On message sent**:

```typescript
mutationFn: sendMessage,
onSuccess: (newMessage) => {
  queryClient.invalidateQueries(['messages', convId])
  queryClient.setQueryData(['message', newMessage.id], newMessage)
}
```

**On document deletion**:

```typescript
mutationFn: deleteDocument,
onSuccess: (docId) => {
  queryClient.invalidateQueries(['documents'])
  queryClient.removeQueries(['document', docId])
  queryClient.removeQueries(['highlights', docId])
}
```

### 4.4 localStorage Usage

**MUST NOT cache server data in localStorage**:

- No caching of documents, highlights, annotations in localStorage
- No caching of conversations or messages
- localStorage is NOT a substitute for React Query

**localStorage MAY be used for UI preferences ONLY**:

- Theme preference (light/dark)
- Sidebar collapse state
- Font size
- Selected document ID (for session restoration)

**Implementation**:

```typescript
// ✅ Allowed: UI preferences
const theme = localStorage.getItem('theme') || 'light'

// ❌ NOT allowed: Server data
// Don't do: localStorage.setItem('documents', JSON.stringify(docs))
```

---

## 6. Accessibility

### 6.1 Web

- Semantic HTML (`<article>`, `<section>`, headings)
- ARIA labels for highlights, buttons
- Keyboard navigation (Tab, Enter, Arrow keys)
- Screen reader support (highlights should be announced)

### 6.2 Mobile

- VoiceOver (iOS) / TalkBack (Android) support
- Sufficient color contrast for highlights
- Touch target sizes ≥ 44pt

---

## 7. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| PDF page load | < 2s | First page rendered |
| EPUB chapter load | < 500ms | Including canonicalization |
| Search interaction | < 300ms | Query input to results |
| Highlight creation | < 500ms | Select → API → render |
| LLM chat response | < 5s | Include context assembly + LLM |

