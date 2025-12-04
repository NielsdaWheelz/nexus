# PDF Implementation Specification

A comprehensive guide for replicating the PDF viewing, highlighting, embedding, and semantic search system from the fractal-chat application.

**Target Audience:** Junior engineers implementing similar functionality in another codebase

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [PDF Viewer Implementation](#pdf-viewer-implementation)
3. [Highlighting System](#highlighting-system)
4. [Text Parsing & Extraction](#text-parsing--extraction)
5. [Vectorization & Embeddings](#vectorization--embeddings)
6. [Database Schema & Storage](#database-schema--storage)
7. [Virtualization & Performance](#virtualization--performance)
8. [Related Features](#related-features)
9. [Dependencies](#dependencies)
10. [Implementation Checklist](#implementation-checklist)

---

## Architecture Overview

This system has five core layers:

```
┌─────────────────────────────────────────────┐
│         User Interface (React)              │
│    (Viewer, Highlights, Popovers)          │
├─────────────────────────────────────────────┤
│    PDF.js Viewer + Custom Highlighting     │
├─────────────────────────────────────────────┤
│  Text Extraction, Chunking, Embedding      │
├─────────────────────────────────────────────┤
│   PostgreSQL + pgvector (Semantic Search)   │
├─────────────────────────────────────────────┤
│  File Storage (Supabase/S3 or similar)     │
└─────────────────────────────────────────────┘
```

**Key Design Principles:**
- Non-invasive highlighting (overlay system, not modifying PDF.js)
- Character offset-based annotation system (consistent across PDFs and HTML)
- Event-driven reactivity (redraws on PDF lifecycle events)
- Graceful degradation (fallback parsers, error handling)
- Performance optimized (lazy loading, batching, virtualization)

---

## PDF Viewer Implementation

### 1.1 Library Choice

**Primary:** `pdfjs-dist` v5.4.296 (Mozilla's PDF.js)

**Why:**
- Industry standard for browser-based PDF rendering
- Active maintenance
- Web Worker support for non-blocking rendering
- Built-in text extraction and event system
- Good browser compatibility

### 1.2 Initialization & Setup

```typescript
import * as pdfjsLib from 'pdfjs-dist/build/pdf.mjs';
import * as pdfjsViewer from 'pdfjs-dist/web/pdf_viewer.mjs';
import { GlobalWorkerOptions } from 'pdfjs-dist/build/pdf.mjs';

// Set worker thread for background processing
GlobalWorkerOptions.workerSrc = `${cdnUrl}/pdf.worker.min.mjs`;

// Create event bus for PDF lifecycle events
const eventBus = new pdfjsViewer.EventBus();

// Create link service (handles internal PDF navigation)
const linkService = new pdfjsViewer.PDFLinkService({ eventBus });

// Create viewer with text layer enabled
const viewer = new pdfjsViewer.PDFViewer({
  container: document.getElementById('pdf-container'),
  eventBus,
  linkService,
  textLayerMode: 1,  // Enable text extraction & selection
  removePageBorders: false,
  textLayerDivBefore: false,
});

linkService.setViewer(viewer);
```

### 1.3 Loading & Rendering PDF

```typescript
async function loadPDF(pdfUrl: string) {
  try {
    // Load PDF document
    const pdf = await pdfjsLib.getDocument(pdfUrl).promise;

    // Set viewer document
    viewer.setDocument(pdf);

    // Set initial scale to fit page width
    viewer.currentScaleValue = 'page-width';

    return pdf;
  } catch (error) {
    console.error('PDF loading failed:', error);
    // Handle error appropriately
  }
}
```

### 1.4 Event Lifecycle & Lifecycle Management

**Key Events to Handle:**

| Event | Purpose | Timing |
|-------|---------|--------|
| `pagesinit` | Pages initialized, PDF ready | Fires once after document loaded |
| `textlayerrendered` | Text layer rendered for a page | After each page renders |
| `pagerendered` | Page rendered to canvas | After page displays |
| `scalechanging` | Before zoom change | During zoom |
| `scalechange` | After zoom change | After zoom completes |
| `pagesloaded` | All pages loaded | On document load completion |

**Event Listener Pattern:**

```typescript
eventBus.on('pagesinit', handlePagesInit);
eventBus.on('textlayerrendered', redrawHighlights);
eventBus.on('pagerendered', logPageRendered);
eventBus.on('scalechanging', handleScaleChanging);
eventBus.on('scalechange', handleScaleChange);

function handlePagesInit() {
  // Initialize highlights after pages loaded
  const container = viewer.container;
  container.style.width = getPreferredWidth();
  redrawHighlights();
}

function redrawHighlights() {
  // Called after text layer renders - critical for highlight visibility
  clearHighlightOverlays();
  annotations.forEach(ann => renderHighlight(ann));
}

// Critical: Clean up on unmount
function cleanup() {
  eventBus.off('pagesinit', handlePagesInit);
  eventBus.off('textlayerrendered', redrawHighlights);
  // ... remove all listeners
  viewer.cleanup();
  pdf.destroy();
}
```

### 1.5 Dynamic Module Loading (Performance)

**Problem:** PDF.js is large (~8MB uncompressed). Loading synchronously blocks initial render.

**Solution:** Lazy load with cached promises

```typescript
let pdfjsLibCache: typeof import('pdfjs-dist/build/pdf.mjs') | null = null;
let pdfjsViewerCache: typeof import('pdfjs-dist/web/pdf_viewer.mjs') | null = null;

async function loadPdfJsModules() {
  if (!pdfjsLibCache) {
    // @vite-ignore tells bundler not to pre-load
    pdfjsLibCache = await import(/* @vite-ignore */ 'pdfjs-dist/build/pdf.mjs');
  }
  if (!pdfjsViewerCache) {
    pdfjsViewerCache = await import(/* @vite-ignore */ 'pdfjs-dist/web/pdf_viewer.mjs');
  }
  return { pdfjsLib: pdfjsLibCache, pdfjsViewer: pdfjsViewerCache };
}
```

---

## Highlighting System

### 2.1 Core Architecture

**Key Concept:** Non-invasive overlay-based highlighting system

**Why not use PDF.js annotations?**
- Built-in annotations are not well-suited for web display
- Overlay approach is simpler and more flexible
- Allows custom styling and animations
- Doesn't require modifying PDF internals

### 2.2 Annotation Data Structure

```typescript
interface Annotation {
  id: string;
  documentId: string;
  userId: string;

  // Character offsets (document-wide, 0-indexed)
  start: number;
  end: number;

  // Context
  quote: string;           // The selected text
  prefix: string;          // 30 chars before
  suffix: string;          // 30 chars after

  // Content
  body?: string;           // Note/comment text
  color?: string;          // Color identifier: 'purple', 'red', etc.

  // Metadata
  visibility: 'private' | 'public';
  createdAt: Date;
  updatedAt: Date;

  // Permissions
  perms: string[];         // User/group IDs with access
}
```

### 2.3 Highlight Rendering Pipeline

**Step 1: Walk DOM to Map Character Offsets**

```typescript
function walkTextNodes(container: HTMLElement): { node: Text; startOffset: number }[] {
  const textPositions: { node: Text; startOffset: number }[] = [];
  const walker = document.createTreeWalker(
    container,
    NodeFilter.SHOW_TEXT,
    null
  );

  let currentOffset = 0;
  let node;

  while ((node = walker.nextNode() as Text)) {
    textPositions.push({
      node,
      startOffset: currentOffset,
    });
    currentOffset += node.textContent?.length ?? 0;
  }

  return textPositions;
}
```

**Step 2: Convert Annotation Offsets to DOM Ranges**

```typescript
function offsetsToRange(
  container: HTMLElement,
  startOffset: number,
  endOffset: number
): Range {
  const range = document.createRange();
  const textPositions = walkTextNodes(container);

  // Find start node
  let startNode: Text | null = null;
  let startNodeOffset = 0;
  for (const pos of textPositions) {
    if (pos.startOffset + pos.node.textContent!.length > startOffset) {
      startNode = pos.node;
      startNodeOffset = startOffset - pos.startOffset;
      break;
    }
  }

  // Find end node (same logic)
  let endNode: Text | null = null;
  let endNodeOffset = 0;
  for (const pos of textPositions) {
    if (pos.startOffset + pos.node.textContent!.length > endOffset) {
      endNode = pos.node;
      endNodeOffset = endOffset - pos.startOffset;
      break;
    }
  }

  if (!startNode || !endNode) return range;

  range.setStart(startNode, startNodeOffset);
  range.setEnd(endNode, endNodeOffset);
  return range;
}
```

**Step 3: Generate Highlight Boxes from Range**

```typescript
function getRectanglesFromRange(range: Range): DOMRect[] {
  // getClientRects() handles multi-line selections automatically
  return Array.from(range.getClientRects());
}
```

**Step 4: Create Overlay Elements**

```typescript
function renderHighlight(
  annotation: Annotation,
  container: HTMLElement,
  scale: number = 1
): void {
  // Get overlay layer (create if doesn't exist)
  let overlayLayer = container.querySelector('.pdfOverlayLayer') as HTMLElement;
  if (!overlayLayer) {
    overlayLayer = document.createElement('div');
    overlayLayer.className = 'pdfOverlayLayer';
    overlayLayer.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      pointer-events: none;
    `;
    container.appendChild(overlayLayer);
  }

  // Get text range
  const range = offsetsToRange(container, annotation.start, annotation.end);
  const rects = getRectanglesFromRange(range);

  // Create div for each rect
  rects.forEach((rect) => {
    const div = document.createElement('div');
    div.className = `highlight highlight-${annotation.color || 'purple'}`;
    div.dataset.annid = annotation.id;

    // Scale and position
    div.style.cssText = `
      position: absolute;
      left: ${rect.left * scale}px;
      top: ${rect.top * scale}px;
      width: ${rect.width * scale}px;
      height: ${rect.height * scale}px;
      background: rgba(168, 122, 245, 0.35);
      mix-blend-mode: multiply;
      border-radius: 2px;
      pointer-events: none;
    `;

    overlayLayer.appendChild(div);
  });
}
```

### 2.4 Styling

```css
.highlight {
  position: absolute;
  background: rgba(168, 122, 245, 0.35);
  mix-blend-mode: multiply;
  border-radius: 2px;
  pointer-events: none;
}

.highlight-purple { background: rgba(168, 122, 245, 0.35); }
.highlight-red { background: rgba(239, 68, 68, 0.35); }
.highlight-green { background: rgba(34, 197, 94, 0.35); }
.highlight-blue { background: rgba(59, 130, 246, 0.35); }
.highlight-orange { background: rgba(249, 115, 22, 0.35); }
.highlight-yellow { background: rgba(234, 179, 8, 0.35); }
.highlight-teal { background: rgba(20, 184, 166, 0.35); }
.highlight-pink { background: rgba(236, 72, 153, 0.35); }
.highlight-brown { background: rgba(120, 53, 15, 0.35); }

/* Interactive effects */
.highlight:hover {
  background: rgba(168, 122, 245, 0.5);
  outline: 2px solid rgba(168, 122, 245, 0.8);
}

.highlight.active {
  background: rgba(168, 122, 245, 0.6);
  outline: 2px solid rgba(168, 122, 245, 1);
}
```

### 2.5 Text Selection & Annotation Creation

```typescript
function handleTextSelection(event: MouseEvent) {
  const selection = window.getSelection();
  if (!selection || selection.toString().length === 0) return;

  // Get selected text and surrounding context
  const selectedText = selection.toString();
  const range = selection.getRangeAt(0);

  // Walk to get character offsets
  const container = document.getElementById('pdf-container')!;
  const textPositions = walkTextNodes(container);

  // Calculate document-wide offsets...
  // (similar to offsetsToRange but in reverse)

  const annotation: Annotation = {
    id: generateId(),
    documentId: currentDocId,
    userId: currentUserId,
    start: startOffset,
    end: endOffset,
    quote: selectedText,
    prefix: getContextBefore(startOffset, 30),
    suffix: getContextAfter(endOffset, 30),
    color: 'purple',
    visibility: 'private',
    createdAt: new Date(),
    updatedAt: new Date(),
    perms: [currentUserId],
  };

  // Show popover for adding note
  showAnnotationPopover(annotation, event.clientX, event.clientY);
}
```

### 2.6 Handling Overlapping Highlights

**Challenge:** Multiple annotations can overlap the same text

**Solution:** Event-based segmentation algorithm

```typescript
interface HighlightEvent {
  type: 'start' | 'end';
  position: number;
  annotationId: string;
}

function renderOverlappingHighlights(annotations: Annotation[], container: HTMLElement) {
  // Create events for all annotations
  const events: HighlightEvent[] = [];
  annotations.forEach(ann => {
    events.push({ type: 'start', position: ann.start, annotationId: ann.id });
    events.push({ type: 'end', position: ann.end, annotationId: ann.id });
  });

  // Sort events by position
  events.sort((a, b) => a.position - b.position);

  // Process events to determine overlaps
  const activeAnnotations = new Set<string>();
  let currentPos = 0;
  const segments: { start: number; end: number; annotationIds: string[] }[] = [];

  for (const event of events) {
    if (event.position > currentPos && activeAnnotations.size > 0) {
      segments.push({
        start: currentPos,
        end: event.position,
        annotationIds: Array.from(activeAnnotations),
      });
    }

    if (event.type === 'start') {
      activeAnnotations.add(event.annotationId);
    } else {
      activeAnnotations.delete(event.annotationId);
    }

    currentPos = event.position;
  }

  // Render each segment
  segments.forEach(segment => {
    // ... render with appropriate styling
  });
}
```

### 2.7 Updating Highlights on PDF Events

```typescript
// In event listener setup
eventBus.on('textlayerrendered', () => {
  // Text layer changed, redraw all highlights
  const overlayLayers = document.querySelectorAll('.pdfOverlayLayer');
  overlayLayers.forEach(layer => layer.innerHTML = '');

  annotations.forEach(ann => renderHighlight(ann, container));
});

eventBus.on('scalechange', (event: { scale: number }) => {
  // Zoom changed, reposition highlights
  const scale = viewer.currentScale;
  document.querySelectorAll('.highlight').forEach(el => {
    const rect = el.getBoundingClientRect();
    el.style.transform = `scale(${scale})`;
  });
});
```

---

## Text Parsing & Extraction

### 3.1 Library Selection

**Primary:** `pdf-parse` v2.4.0

**Reason:**
- Pure Node.js, no native dependencies
- Reliable text extraction
- Good for production PDF workflows
- Fast processing

**Fallback:** `pdfjs-dist` (server-side)

### 3.2 Server-Side PDF Text Extraction

```typescript
import pdfParse from 'pdf-parse';
import * as pdfjsLib from 'pdfjs-dist/legacy/build/pdf.mjs';

interface ExtractionResult {
  text: string;
  metadata: {
    author?: string;
    createdDate?: Date;
    modifiedDate?: Date;
    version?: string;
  };
  pages: string[];
  error?: string;
}

async function extractPdfText(pdfBuffer: Buffer): Promise<ExtractionResult> {
  try {
    // Try primary parser
    const data = await pdfParse(pdfBuffer, {
      itemJoiner: ' ',      // Join text items with space
      pageJoiner: '\n\n',   // Join pages with double newline
      lineEnforce: true,     // Preserve line breaks
    });

    const text = normalizePdfText(data.text);
    const metadata = extractPdfMetadata(data.info);
    const pages = data.text.split('\n\n').map(normalizePdfText);

    return { text, metadata, pages };
  } catch (error) {
    // Fallback to PDF.js
    console.warn('pdf-parse failed, trying PDF.js fallback:', error);
    return extractPdfTextWithPdfJs(pdfBuffer);
  }
}

function normalizePdfText(text: string): string {
  return text
    .replace(/\r\n/g, '\n')      // Windows newlines
    .replace(/\r/g, '\n')         // Old Mac newlines
    .replace(/\f/g, '\n\n')       // Form feeds
    .replace(/\u00A0/g, ' ')      // Non-breaking spaces
    .replace(/ {2,}/g, ' ')       // Multiple spaces to single
    .replace(/\n{3,}/g, '\n\n')   // Collapse 3+ newlines
    .trim();
}

function extractPdfMetadata(info: any) {
  return {
    author: extractAuthor(info),
    createdDate: extractDate(info?.CreationDate || info?.['xap:CreateDate']),
    modifiedDate: extractDate(info?.ModDate),
    version: info?.PDFFormatVersion,
  };
}

function extractAuthor(info: any): string | undefined {
  // Try multiple common author fields
  const authorFields = [
    'Author',
    'creator',
    'dc:creator',
    'meta:author',
  ];
  return authorFields
    .map(field => info?.[field])
    .find(val => val !== undefined);
}

function extractDate(dateStr?: string): Date | undefined {
  if (!dateStr) return undefined;
  try {
    return new Date(dateStr);
  } catch {
    return undefined;
  }
}
```

### 3.3 Fallback: PDF.js Server-Side Extraction

```typescript
async function extractPdfTextWithPdfJs(pdfBuffer: Buffer): Promise<ExtractionResult> {
  const pdf = await pdfjsLib.getDocument(pdfBuffer).promise;
  const pages: string[] = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const textContent = await page.getTextContent();
    const pageText = textContent.items
      .map((item: any) => item.str)
      .join(' ');
    pages.push(pageText);
  }

  const text = normalizePdfText(pages.join('\n\n'));

  return {
    text,
    pages,
    metadata: { author: undefined },
  };
}
```

### 3.4 Integration with Document Ingestion

```typescript
async function uploadAndProcessPdf(
  pdfBuffer: Buffer,
  userId: string,
  title: string,
) {
  // Extract text
  const extraction = await extractPdfText(pdfBuffer);
  if (extraction.error) {
    throw new Error(`PDF extraction failed: ${extraction.error}`);
  }

  // Create document record
  const documentId = generateId();
  await db.insert(documentTable).values({
    id: documentId,
    title,
    textContent: extraction.text,
    content: '', // Empty for PDFs
    url: `${storageBucket}/${documentId}.pdf`,
    publishedTime: extraction.metadata.createdDate?.toISOString(),
    createdAt: new Date(),
    updatedAt: new Date(),
  });

  // Upload file to storage
  const storageUrl = await uploadToStorage(
    `${documentId}.pdf`,
    pdfBuffer,
    'documents'
  );

  // Chunk and embed (see Vectorization section)
  await chunkAndEmbed(documentId, extraction.text, userId);

  return { documentId, extraction };
}
```

---

## Vectorization & Embeddings

### 4.1 Architecture Overview

**Components:**
1. Text chunking (LangChain RecursiveCharacterTextSplitter)
2. Embedding generation (OpenAI text-embedding-3-small)
3. Vector storage (PostgreSQL + pgvector)
4. Semantic search (vector similarity search)

### 4.2 Text Chunking Strategy

```typescript
import { RecursiveCharacterTextSplitter } from '@langchain/text-splitters';

async function chunkText(text: string): Promise<string[]> {
  const splitter = new RecursiveCharacterTextSplitter({
    chunkSize: 500,      // Characters per chunk
    chunkOverlap: 50,    // 10% overlap for context
    separators: [
      '\n\n',      // Paragraph breaks
      '\n',        // Line breaks
      ' ',         // Words
      '',          // Characters as fallback
    ],
  });

  const chunks = await splitter.splitText(text);
  return chunks.filter(chunk => chunk.trim().length > 0);
}
```

**Why these settings?**
- **500 chars:** ~100-150 tokens (OpenAI models), good semantic coherence
- **50 char overlap:** Captures context across chunk boundaries
- **Separators:** Respects document structure (paragraphs → lines → words → chars)

### 4.3 Embedding Generation

```typescript
import { openai } from '@ai-sdk/openai';
import { embedMany } from 'ai';

interface EmbeddingConfig {
  model: ReturnType<typeof openai.textEmbeddingModel>;
  dimensions: number;
  maxParallelCalls: number;
}

const embeddingConfig: EmbeddingConfig = {
  model: openai.textEmbeddingModel('text-embedding-3-small'),
  dimensions: 512,          // Dimensions returned by the model
  maxParallelCalls: 100,    // Parallel API calls
};

async function generateEmbeddings(texts: string[]): Promise<number[][]> {
  const embeddings = await embedMany({
    model: embeddingConfig.model,
    texts,
  });

  return embeddings.embeddings;
}
```

### 4.4 Full Chunking & Embedding Pipeline

```typescript
async function chunkAndEmbed(
  documentId: string,
  text: string,
  userId: string,
): Promise<void> {
  // Step 1: Chunk text
  const chunks = await chunkText(text);
  console.log(`Chunked into ${chunks.length} pieces`);

  // Step 2: Generate embeddings
  const embeddings = await generateEmbeddings(chunks);
  console.log(`Generated ${embeddings.length} embeddings`);

  // Step 3: Store in database
  const chunkRecords = chunks.map((text, index) => ({
    id: generateId(),
    documentId,
    text,
    chunkIndex: index,
    embedding: embeddings[index],
    createdAt: new Date(),
    updatedAt: new Date(),
  }));

  // Batch insert (usually more efficient than individual inserts)
  await db.insert(documentChunksTable).values(chunkRecords);

  console.log(`Stored ${chunkRecords.length} chunks with embeddings`);
}
```

### 4.5 Semantic Search

```typescript
async function semanticSearch(
  query: string,
  topK: number = 5,
  documentIds?: string[],
): Promise<SearchResult[]> {
  // Step 1: Embed query
  const [queryEmbedding] = await generateEmbeddings([query]);

  // Step 2: Vector similarity search in database
  const pgvectorQuery = buildPgvectorQuery(
    queryEmbedding,
    topK,
    documentIds
  );

  const results = await db.execute(pgvectorQuery);

  // Step 3: Return with similarity scores
  return results.map(row => ({
    documentId: row.document_id,
    documentTitle: row.title,
    chunk: row.text,
    chunkIndex: row.chunk_index,
    similarity: row.similarity,
  }));
}

function buildPgvectorQuery(
  embedding: number[],
  topK: number,
  documentIds?: string[],
): string {
  const vectorStr = `[${embedding.join(',')}]::vector`;

  const sqlQuery = `
    SELECT
      dc.id,
      dc.document_id,
      dc.text,
      dc.chunk_index,
      d.title,
      1 - (dc.embedding <=> ${vectorStr}) as similarity
    FROM document_chunks dc
    INNER JOIN document d ON dc.document_id = d.id
    ${documentIds ? `WHERE dc.document_id = ANY($1)` : ''}
    ORDER BY dc.embedding <=> ${vectorStr}
    LIMIT ${topK}
  `;

  return sqlQuery;
}

interface SearchResult {
  documentId: string;
  documentTitle: string;
  chunk: string;
  chunkIndex: number;
  similarity: number;
}
```

### 4.6 Integration with Document Upload

```typescript
async function handleDocumentUpload(
  file: File,
  userId: string,
): Promise<{ documentId: string; chunks: number }> {
  // 1. Validate file
  if (!file.name.endsWith('.pdf')) {
    throw new Error('Only PDF files supported');
  }

  // 2. Extract text
  const buffer = await file.arrayBuffer();
  const extraction = await extractPdfText(new Uint8Array(buffer));

  // 3. Create document record
  const documentId = generateId();
  await db.insert(documentTable).values({
    id: documentId,
    title: file.name,
    content: '',
    textContent: extraction.text,
    createdAt: new Date(),
    updatedAt: new Date(),
  });

  // 4. Chunk and embed
  const chunks = await chunkText(extraction.text);
  await chunkAndEmbed(documentId, extraction.text, userId);

  // 5. Upload file to storage
  const url = await uploadToStorage(
    `${documentId}.pdf`,
    new Uint8Array(buffer),
    'documents'
  );

  // 6. Update document with storage URL
  await db.update(documentTable)
    .set({ url })
    .where(eq(documentTable.id, documentId));

  return { documentId, chunks: chunks.length };
}
```

---

## Database Schema & Storage

### 5.1 PostgreSQL Schema Design

**Prerequisites:**
- PostgreSQL 15+
- pgvector extension installed: `CREATE EXTENSION IF NOT EXISTS vector;`

### 5.2 Core Tables

**Table: `document`**

Purpose: Store document metadata and content

```typescript
import { pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const documentTable = pgTable('document', {
  id: text('id').primaryKey(),

  // Content
  title: text('title').notNull(),
  content: text('content').notNull(),  // HTML for web docs, empty for PDFs
  textContent: text('text_content'),   // Plain text for search

  // Storage
  url: text('url'),  // Storage URL (Supabase, S3, etc.)

  // Metadata
  publishedTime: text('published_time'),  // ISO 8601 date string

  // Timestamps
  createdAt: timestamp('created_at', { withTimezone: true }).notNull(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull(),
});
```

**Table: `document_chunks`**

Purpose: Store chunked text with embeddings for semantic search

```typescript
import { pgTable, text, integer, timestamp, vector } from 'drizzle-orm/pg-core';
import { documentTable } from './documents';

export const documentChunksTable = pgTable('document_chunks', {
  id: text('id').primaryKey(),

  // Relationship
  documentId: text('document_id')
    .notNull()
    .references(() => documentTable.id, { onDelete: 'cascade' }),

  // Content
  text: text('text').notNull(),  // Chunk content
  chunkIndex: integer('chunk_index').notNull(),  // Position in document

  // Vector embedding (pgvector type)
  embedding: vector('embedding', { dimensions: 512 }).notNull(),

  // Timestamps
  createdAt: timestamp('created_at', { withTimezone: true }).notNull(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull(),
});

// Create index for faster vector similarity search
// In migration:
// CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Table: `annotation`**

Purpose: Store user highlights and notes

```typescript
import { pgTable, text, integer, timestamp } from 'drizzle-orm/pg-core';
import { documentTable } from './documents';

export const annotationTable = pgTable('annotation', {
  id: text('id').primaryKey(),

  // Relationships
  userId: text('user_id')
    .notNull()
    .references(() => userTable.id, { onDelete: 'cascade' }),
  documentId: text('document_id')
    .notNull()
    .references(() => documentTable.id, { onDelete: 'cascade' }),

  // Content
  body: text('body'),  // Note/comment text
  color: text('color'),  // Color identifier

  // Position in document (character offsets)
  start: integer('start').notNull(),  // Start character offset
  end: integer('end').notNull(),      // End character offset

  // Context
  quote: text('quote'),   // Selected text
  prefix: text('prefix'), // 30 chars before
  suffix: text('suffix'), // 30 chars after

  // Access control
  visibility: text('visibility').notNull(),  // 'private' | 'public'
  perms: text('perms').array(),  // User/group IDs with access

  // Timestamps
  createdAt: timestamp('created_at', { withTimezone: true }).notNull(),
  updatedAt: timestamp('updated_at', { withTimezone: true }).notNull(),
});
```

### 5.3 Vector Search Implementation

```typescript
// Raw SQL for semantic search
async function semanticSearch(
  queryEmbedding: number[],
  topK: number = 5,
  documentIds?: string[],
) {
  const vectorStr = `[${queryEmbedding.join(',')}]`;

  let query = `
    SELECT
      dc.id,
      dc.document_id,
      dc.text,
      dc.chunk_index,
      d.title,
      d.url,
      1 - (dc.embedding <=> $1::vector) as similarity
    FROM document_chunks dc
    INNER JOIN document d ON dc.document_id = d.id
  `;

  const params: any[] = [vectorStr];

  if (documentIds && documentIds.length > 0) {
    query += ` WHERE dc.document_id = ANY($${params.length + 1})`;
    params.push(documentIds);
  }

  query += ` ORDER BY dc.embedding <=> $1::vector LIMIT ${topK}`;

  return db.execute(sql`${sql.raw(query)}`, params);
}

// Using Drizzle ORM (recommended):
import { cosineDistance } from 'drizzle-orm';

async function semanticSearchDrizzle(
  queryEmbedding: number[],
  topK: number = 5,
  documentIds?: string[],
) {
  let query = db
    .select({
      id: documentChunksTable.id,
      documentId: documentChunksTable.documentId,
      text: documentChunksTable.text,
      chunkIndex: documentChunksTable.chunkIndex,
      title: documentTable.title,
      url: documentTable.url,
      similarity: cosineDistance(
        documentChunksTable.embedding,
        queryEmbedding
      ),
    })
    .from(documentChunksTable)
    .innerJoin(documentTable, eq(documentChunksTable.documentId, documentTable.id));

  if (documentIds && documentIds.length > 0) {
    query = query.where(
      inArray(documentChunksTable.documentId, documentIds)
    );
  }

  return query
    .orderBy((t) => cosineDistance(t.embedding, queryEmbedding))
    .limit(topK);
}
```

### 5.4 File Storage Architecture

**Options:**

**Option A: Supabase Storage (Recommended for ease)**

```typescript
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
);

async function uploadPdfToStorage(
  documentId: string,
  pdfBuffer: Buffer,
): Promise<string> {
  const { data, error } = await supabase.storage
    .from('documents')
    .upload(`${documentId}.pdf`, pdfBuffer, {
      cacheControl: '3600',
      upsert: false,
    });

  if (error) throw error;

  // Get public URL
  const { data: urlData } = supabase.storage
    .from('documents')
    .getPublicUrl(`${documentId}.pdf`);

  return urlData.publicUrl;
}

async function downloadPdfFromStorage(documentId: string): Promise<ArrayBuffer> {
  const { data, error } = await supabase.storage
    .from('documents')
    .download(`${documentId}.pdf`);

  if (error) throw error;
  return data.arrayBuffer();
}
```

**Option B: AWS S3**

```typescript
import { S3Client, PutObjectCommand, GetObjectCommand } from '@aws-sdk/client-s3';

const s3 = new S3Client({ region: process.env.AWS_REGION });

async function uploadPdfToS3(
  documentId: string,
  pdfBuffer: Buffer,
): Promise<string> {
  const command = new PutObjectCommand({
    Bucket: process.env.S3_BUCKET!,
    Key: `documents/${documentId}.pdf`,
    Body: pdfBuffer,
    ContentType: 'application/pdf',
  });

  await s3.send(command);

  return `https://${process.env.S3_BUCKET}.s3.amazonaws.com/documents/${documentId}.pdf`;
}

async function downloadPdfFromS3(documentId: string): Promise<Buffer> {
  const command = new GetObjectCommand({
    Bucket: process.env.S3_BUCKET!,
    Key: `documents/${documentId}.pdf`,
  });

  const response = await s3.send(command);
  return Buffer.from(await response.Body!.transformToByteArray());
}
```

### 5.5 Annotation CRUD Operations

```typescript
// Create annotation
async function createAnnotation(annotation: Annotation) {
  return db.insert(annotationTable).values({
    ...annotation,
    createdAt: new Date(),
    updatedAt: new Date(),
  });
}

// Get annotations for document
async function getDocumentAnnotations(
  documentId: string,
  userId: string,
): Promise<Annotation[]> {
  return db
    .select()
    .from(annotationTable)
    .where(
      and(
        eq(annotationTable.documentId, documentId),
        or(
          eq(annotationTable.userId, userId),
          eq(annotationTable.visibility, 'public'),
        ),
      ),
    )
    .orderBy(annotationTable.start);
}

// Update annotation
async function updateAnnotation(
  annotationId: string,
  updates: Partial<Annotation>,
) {
  return db
    .update(annotationTable)
    .set({ ...updates, updatedAt: new Date() })
    .where(eq(annotationTable.id, annotationId));
}

// Delete annotation
async function deleteAnnotation(annotationId: string) {
  return db
    .delete(annotationTable)
    .where(eq(annotationTable.id, annotationId));
}
```

---

## Virtualization & Performance

### 6.1 PDF.js Built-in Virtualization

**How PDF.js Virtualizes:**
- Only renders visible pages + 1 page buffer above/below
- Disposes pages that scroll out of view
- Uses web workers for rendering (non-blocking)

**You don't need to implement this yourself** - it's built into `PDFViewer`

```typescript
// PDF.js automatically handles page culling
// Listening to events allows you to respond to virtual page changes

eventBus.on('pagechanging', (event) => {
  console.log(`Page ${event.pageNumber} is now visible`);
  // Update UI, log analytics, etc.
});
```

### 6.2 Highlighting Performance Optimization

**Problem:** Redrawing hundreds of highlights on every text layer render is slow

**Solutions:**

**1. Batch Processing**

```typescript
function renderHighlightsBatch(annotations: Annotation[], container: HTMLElement) {
  // Create all highlight elements first
  const fragment = document.createDocumentFragment();

  annotations.forEach(ann => {
    const overlayDiv = createHighlightElement(ann);
    fragment.appendChild(overlayDiv);
  });

  // Single DOM update
  const layer = container.querySelector('.pdfOverlayLayer')!;
  layer.appendChild(fragment);
}
```

**2. Debounce Redraw**

```typescript
let redrawTimeout: NodeJS.Timeout | null = null;

function scheduleRedraw() {
  if (redrawTimeout) clearTimeout(redrawTimeout);

  redrawTimeout = setTimeout(() => {
    redrawHighlights();
    redrawTimeout = null;
  }, 100);  // Batch updates within 100ms
}

eventBus.on('textlayerrendered', scheduleRedraw);
eventBus.on('pagerendered', scheduleRedraw);
```

**3. Memoization for Scale Calculations**

```typescript
interface CachedScale {
  scale: number;
  matrix: DOMMatrix;
  timestamp: number;
}

let scaleCache: CachedScale | null = null;

function getElementScale(element: HTMLElement): number {
  const scale = viewer.currentScale;

  if (scaleCache && scaleCache.scale === scale) {
    // Return cached matrix if scale hasn't changed
    return scaleCache.matrix.a;
  }

  // Recalculate only when scale changes
  const matrix = new DOMMatrixReadOnly(
    `matrix(${scale}, 0, 0, ${scale}, 0, 0)`
  );

  scaleCache = { scale, matrix, timestamp: Date.now() };
  return matrix.a;
}
```

**4. Use CSS Transform Instead of Layout**

```typescript
// ❌ SLOW: Updates layout
highlight.style.left = `${rect.left * scale}px`;
highlight.style.top = `${rect.top * scale}px`;

// ✅ FAST: Uses GPU acceleration
highlight.style.transform = `translate(${rect.left}px, ${rect.top}px) scale(${scale})`;
highlight.style.willChange = 'transform';
```

### 6.3 Module Loading Strategy

**Goals:**
- Don't block initial page load
- Cache loaded modules
- Load in background if not immediately needed

```typescript
// Lazy load PDF.js
let loadPromise: Promise<{
  pdfjsLib: typeof import('pdfjs-dist/build/pdf.mjs');
  pdfjsViewer: typeof import('pdfjs-dist/web/pdf_viewer.mjs');
}> | null = null;

async function loadPdfJsIfNeeded() {
  if (loadPromise) return loadPromise;

  loadPromise = Promise.all([
    import(/* @vite-ignore */ 'pdfjs-dist/build/pdf.mjs'),
    import(/* @vite-ignore */ 'pdfjs-dist/web/pdf_viewer.mjs'),
  ]).then(([pdfjsLib, pdfjsViewer]) => ({
    pdfjsLib,
    pdfjsViewer,
  }));

  return loadPromise;
}

// In component:
const { pdfjsLib, pdfjsViewer } = await loadPdfJsIfNeeded();
```

### 6.4 Cleanup & Memory Management

**Critical:** Properly cleanup when component unmounts

```typescript
function PdfViewer({ documentId }: { documentId: string }) {
  useEffect(() => {
    let viewerInstance: any = null;
    let pdfDocument: any = null;

    async function initViewer() {
      const { pdfjsLib, pdfjsViewer } = await loadPdfJsIfNeeded();

      viewerInstance = new pdfjsViewer.PDFViewer({
        container: containerRef.current!,
        eventBus: new pdfjsViewer.EventBus(),
      });

      pdfDocument = await pdfjsLib.getDocument(pdfUrl).promise;
      viewerInstance.setDocument(pdfDocument);
    }

    initViewer();

    // Cleanup on unmount
    return () => {
      if (viewerInstance) {
        // Clean up event listeners
        viewerInstance.eventBus.off('pagesinit', handlePageInit);

        // Destroy viewer
        viewerInstance.cleanup?.();
      }

      if (pdfDocument) {
        // Clean up PDF document
        pdfDocument.destroy();
        pdfDocument.cleanup?.();
      }
    };
  }, [documentId]);

  return <div ref={containerRef} />;
}
```

---

## Related Features

### 7.1 Selection & Annotation Popovers

```typescript
// CustomPopover.tsx
interface PopoverProps {
  selectedText: string;
  position: { x: number; y: number };
  onAddAnnotation: (annotation: Annotation, note: string) => Promise<void>;
  onAddToChat: (text: string) => Promise<void>;
}

export function CustomPopover({
  selectedText,
  position,
  onAddAnnotation,
  onAddToChat,
}: PopoverProps) {
  return (
    <div
      style={{
        position: 'fixed',
        left: `${position.x}px`,
        top: `${position.y}px`,
        zIndex: 1000,
      }}
      className="cyberpunk-glassmorphic-popover"
    >
      <button onClick={() => showColorPicker()}>
        Add Highlight
      </button>
      <button onClick={() => onAddToChat(selectedText)}>
        Add to Chat
      </button>
      <button onClick={() => tweetAnnotation(selectedText)}>
        Share
      </button>
    </div>
  );
}
```

### 7.2 Annotation Sidebar

```typescript
export function AnnotationList({ documentId, userId }: AnnotationListProps) {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);

  useEffect(() => {
    async function fetchAnnotations() {
      const anns = await getDocumentAnnotations(documentId, userId);
      // Sort by start position
      setAnnotations(anns.sort((a, b) => a.start - b.start));
    }
    fetchAnnotations();
  }, [documentId, userId]);

  return (
    <div className="annotation-list">
      {annotations.map(ann => (
        <div
          key={ann.id}
          className={`annotation-item annotation-${ann.color}`}
          onClick={() => scrollToAnnotation(ann.start)}
        >
          <p className="quote">"{ann.quote}"</p>
          {ann.body && <p className="note">{ann.body}</p>}
        </div>
      ))}
    </div>
  );
}
```

### 7.3 AI Chat Integration with Semantic Search

```typescript
// api.chat.ts - Server action for chat with semantic search

async function handleChatWithSemanticSearch(
  message: string,
  documentIds: string[],
  userId: string,
) {
  // 1. Embed user query
  const [queryEmbedding] = await generateEmbeddings([message]);

  // 2. Search for relevant chunks
  const chunks = await semanticSearch(queryEmbedding, topK: 5, documentIds);

  // 3. Build context for LLM
  const context = chunks
    .map(c => `[${c.documentTitle}] ${c.chunk}`)
    .join('\n\n');

  // 4. Call LLM with context + query
  const response = await openai.chat.completions.create({
    model: 'gpt-4o-mini',
    messages: [
      {
        role: 'system',
        content: `You are a critical, terse, philosophical document analyst.
Use the provided context to answer questions about documents.
Context:\n${context}`,
      },
      { role: 'user', content: message },
    ],
  });

  return response.choices[0].message.content;
}
```

---

## Dependencies

### 8.1 Complete Package.json Entries

```json
{
  "dependencies": {
    "pdfjs-dist": "^5.4.296",
    "pdf-parse": "^2.4.0",
    "@types/pdf-parse": "^1.1.5",
    "drizzle-orm": "^0.44.5",
    "postgres": "^3.4.7",
    "@supabase/supabase-js": "^2.58.0",
    "@ai-sdk/openai": "^2.0.42",
    "ai": "^5.0.59",
    "openai": "^6.1.0",
    "@langchain/text-splitters": "^0.3.7",
    "langchain": "^0.3.35",
    "@langchain/core": "^0.3.78",
    "react": "^19.1.1",
    "react-dom": "^19.1.1",
    "zod": "^4.1.12",
    "framer-motion": "^12.23.22"
  },
  "devDependencies": {
    "typescript": "^5.9.2",
    "@types/node": "^20.0.0"
  }
}
```

### 8.2 Environment Variables

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJxxxxx
SUPABASE_BUCKET=documents

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# AWS S3 (optional, instead of Supabase)
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=my-documents
```

---

## Implementation Checklist

Use this checklist to track your implementation:

### Phase 1: Core PDF Viewing
- [ ] Install `pdfjs-dist` and types
- [ ] Create PDFViewer component with PDF.js initialization
- [ ] Set up event bus and event listeners
- [ ] Implement dynamic module loading
- [ ] Test PDF loading and page navigation
- [ ] Test zoom/scale functionality
- [ ] Add cleanup on component unmount

### Phase 2: Text Extraction
- [ ] Install `pdf-parse` and `pdfjs-dist`/legacy
- [ ] Implement `extractPdfText()` with primary parser
- [ ] Implement fallback to PDF.js server-side extraction
- [ ] Add metadata extraction (author, dates)
- [ ] Test with various PDF formats (scanned, text-based, etc.)
- [ ] Add error handling and logging

### Phase 3: Basic Highlighting
- [ ] Create Annotation data structure
- [ ] Implement text node walking with character offsets
- [ ] Implement offset-to-DOM-Range conversion
- [ ] Create overlay layer system
- [ ] Render highlights from annotations
- [ ] Add highlight styling and colors
- [ ] Test multi-line highlights
- [ ] Test overlapping highlights

### Phase 4: Text Selection & Annotation Creation
- [ ] Implement text selection detection
- [ ] Calculate character offsets from selection
- [ ] Extract context (prefix/suffix)
- [ ] Create popover UI for annotation
- [ ] Handle annotation creation (DB insert)
- [ ] Test on different PDF pages

### Phase 5: Database Setup
- [ ] Create PostgreSQL database
- [ ] Install pgvector extension
- [ ] Implement Drizzle ORM schema
- [ ] Create migrations for tables
- [ ] Test basic CRUD operations on annotations
- [ ] Create indexes for performance

### Phase 6: Text Chunking & Vectorization
- [ ] Install LangChain and OpenAI SDK
- [ ] Implement `chunkText()` with RecursiveCharacterTextSplitter
- [ ] Implement `generateEmbeddings()` with OpenAI
- [ ] Create full `chunkAndEmbed()` pipeline
- [ ] Test chunking with sample PDFs
- [ ] Verify embeddings are generated correctly
- [ ] Test batch processing

### Phase 7: Semantic Search
- [ ] Create pgvector indexes
- [ ] Implement vector similarity search
- [ ] Test search with sample queries
- [ ] Measure search performance
- [ ] Add query embedding caching (optional optimization)

### Phase 8: File Storage
- [ ] Choose storage solution (Supabase/S3)
- [ ] Implement upload function
- [ ] Implement download function
- [ ] Test file upload/download
- [ ] Set up public URL generation
- [ ] Add file cleanup on document deletion

### Phase 9: UI Integration
- [ ] Create CustomPopover component
- [ ] Create NotePopover component
- [ ] Create AnnotationList sidebar component
- [ ] Implement annotation click-to-scroll
- [ ] Add highlight hover effects
- [ ] Test responsiveness

### Phase 10: Performance & Cleanup
- [ ] Implement highlight rendering batching
- [ ] Add debouncing for redraw events
- [ ] Implement scale calculation memoization
- [ ] Add CSS transforms instead of layout updates
- [ ] Test with large PDFs (100+ pages, 1000+ annotations)
- [ ] Profile and optimize slow sections
- [ ] Verify memory cleanup

### Phase 11: Testing
- [ ] Unit tests for text extraction
- [ ] Unit tests for chunking
- [ ] Unit tests for embedding
- [ ] Integration tests for annotation CRUD
- [ ] E2E tests for highlighting workflow
- [ ] Performance tests with large datasets

### Phase 12: Deployment
- [ ] Set up database migrations
- [ ] Configure environment variables
- [ ] Deploy storage bucket
- [ ] Set up vector search indexes
- [ ] Test in production environment
- [ ] Set up monitoring/logging
- [ ] Document API endpoints

---

## Troubleshooting Guide

### PDF Not Rendering

**Symptom:** Blank page or "PDF failed to load"

**Solutions:**
1. Check CORS headers if loading from external URL
2. Verify PDF.js worker is loading: check Network tab for `pdf.worker.min.mjs`
3. Check browser console for errors
4. Try with a known-good PDF file
5. Verify PDF is not corrupted: `pdfinfo` command

### Highlights Not Appearing

**Symptom:** Annotations in database but not visible on PDF

**Solutions:**
1. Verify character offsets are correct:
   - Breakpoint in rendering code and log `start/end` values
   - Check if they're within document length
2. Verify overlay layer is created:
   - Inspect DOM for `.pdfOverlayLayer` div
3. Check highlight styling:
   - Inspect computed styles of highlight divs
   - Verify `pointer-events: none` isn't blocking clicks
4. Verify event listener is attached:
   - Add logging in `textlayerrendered` handler

### Vectorization Failing

**Symptom:** Chunks not being embedded or stored

**Solutions:**
1. Check OpenAI API key and quota
2. Verify database connection
3. Check chunk count: too many concurrent API calls?
4. Add detailed logging to `chunkAndEmbed()`
5. Verify pgvector extension is installed: `SELECT * FROM pg_extension WHERE extname = 'vector';`

### Search Returns No Results

**Symptom:** Semantic search query returns empty results

**Solutions:**
1. Verify chunks were created: `SELECT COUNT(*) FROM document_chunks;`
2. Verify embeddings are non-null: `SELECT COUNT(*) FROM document_chunks WHERE embedding IS NULL;`
3. Test with exact chunk text first (sanity check)
4. Check similarity threshold: maybe results have low similarity
5. Verify vector dimensions match: `SELECT dimensions FROM document_chunks LIMIT 1;`

---

## References & Resources

**PDF.js Documentation:**
- https://mozilla.github.io/pdf.js/getting_started/
- https://github.com/mozilla/pdf.js

**pgvector Documentation:**
- https://github.com/pgvector/pgvector
- Similarity search guide: https://github.com/pgvector/pgvector#querying

**OpenAI Embeddings:**
- https://platform.openai.com/docs/guides/embeddings
- Model comparison: text-embedding-3-small vs text-embedding-3-large

**LangChain Text Splitters:**
- https://js.langchain.com/docs/modules/data_connection/document_loaders/
- https://github.com/langchain-ai/langchainjs

**Drizzle ORM with pgvector:**
- https://orm.drizzle.team/docs/sql-operators
- Vector operators: https://github.com/drizzle-team/drizzle-orm/blob/main/docs/pg-core.md

---

## Additional Notes

### Character Offsets vs DOM Paths

This implementation uses **character offsets** (positions in the full document text) rather than DOM paths. This approach:

**Advantages:**
- Consistent across PDF and HTML documents
- Survives DOM structure changes (re-rendering, etc.)
- Easy to persist and share

**Disadvantages:**
- Requires walking all text nodes to calculate offsets
- Can be slow on very large documents (optimize with caching)

### Why Overlays Instead of PDF Annotations?

PDF.js has built-in annotation support, but using overlays is better because:
- More control over styling and interactions
- Easier to implement custom features (animations, popovers)
- Works consistently across browser implementations
- Can use HTML/CSS for rich interactivity

### Scaling Embeddings to Production

For large-scale deployment:
1. **Batch uploads:** Use job queues (Bull, RabbitMQ) for embedding generation
2. **Vector indexing:** Use HNSW indexes in pgvector for faster search
3. **Caching:** Cache recent search results
4. **Replication:** Consider read replicas for search-heavy workloads
5. **Monitoring:** Track embedding generation time and search latency
