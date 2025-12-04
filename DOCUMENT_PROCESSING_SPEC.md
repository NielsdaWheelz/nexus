# Document Processing Implementation Spec

Complete guide for implementing document upload, extraction, parsing, chunking, and embedding across PDFs, EPUBs, and web articles.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Document Upload](#document-upload)
3. [Content Extraction by Type](#content-extraction-by-type)
4. [Text Normalization & Chunking](#text-normalization--chunking)
5. [Embedding Generation](#embedding-generation)
6. [Storage Systems](#storage-systems)
7. [Database Schema](#database-schema)
8. [API Endpoints](#api-endpoints)
9. [Complete Workflows](#complete-workflows)
10. [Dependencies & Configuration](#dependencies--configuration)

---

## Architecture Overview

The document processing pipeline handles three document types:

```
User Input (PDF/EPUB/URL)
         ↓
    File Upload/Fetch
         ↓
Content Extraction (type-specific)
         ↓
Text Normalization
         ↓
Metadata Resolution
         ↓
Text Chunking
         ↓
Embedding Generation
         ↓
Database Storage (metadata + chunks + vectors)
         ↓
File Storage (original file in object store)
         ↓
Indexed for Semantic Search
```

---

## Document Upload

### Frontend File Upload

**Component**: `app/components/upload-form.tsx`

Drag-and-drop form for local files:
- Accepts `.pdf` and `.epub` files
- Max file size: 15 MB
- Posts multipart form data to `/api/upload`

**Component**: `app/components/ui/file-upload.tsx`

Reusable composable upload component:
- Exports: `FileUpload`, `FileUploadTrigger`, `FileUploadContent`
- Drag-and-drop support
- Multiple file selection

**Hook**: `app/hooks/use-file-upload.ts`

React hook for upload state management:
- File validation
- Drag-and-drop handling
- Callbacks: `onFilesChange`, `onFilesAdded`

### API Upload Endpoint

**Route**: `POST /api/upload`

**File**: `app/routes/api.upload.ts`

**Handler**: `action()` function

**Process**:

1. **Authentication Check**
   - Verify user session
   - Get user ID

2. **Billing Validation**
   - Check document allowance vs. current document count
   - Enforce per-user limits based on Stripe tier

3. **File Type Detection**
   - Use `fileTypeFromBuffer()` to detect MIME type
   - Support: `application/pdf`, `application/epub+zip`
   - Reject unsupported types

4. **Format-Specific Processing**

   **For PDFs**:
   - Extract text via `extractPdfText()`
   - Extract metadata (author, creation date)
   - Store in `document` table
   - Generate chunks and embeddings
   - Upload to Supabase storage

   **For EPUBs**:
   - Parse using `epub2` library
   - Extract chapter HTML and text
   - Combine all chapters into single text
   - Extract metadata from EPUB manifest
   - Store in `document` table
   - Generate chunks and embeddings
   - Upload to Supabase storage

5. **Redirect**
   - Send to document view page

**Input**: Multipart form data
```
Content-Type: multipart/form-data
file: <binary file data>
```

**Output**: Redirect to `/document/{documentId}`

---

## Content Extraction by Type

### PDF Extraction

**File**: `app/server/pdf-extractor.server.ts`

**Main Function**: `extractPdfText(buffer: Buffer)`

**Primary Method**:
- Library: `pdf-parse`
- Extracts full text from PDF
- Retrieves metadata (author, creation date, producer, etc.)

**Fallback Method**:
- Library: `pdfjs-dist`
- Used if primary extraction fails
- Page-by-page text extraction
- More robust for malformed PDFs

**Text Processing**:
- Remove carriage returns (`\r`)
- Remove form feeds (`\f`)
- Collapse multiple newlines to single newline
- Trim whitespace

**Output**:
```typescript
{
  text: string              // Full extracted text
  metadata: {
    author?: string
    creationDate?: string
    producer?: string
    modDate?: string
  }
}
```

**Error Handling**:
- Custom `PdfExtractionError` class
- Fallback to pdfjs-dist if pdf-parse fails
- Throws if both methods fail

### EPUB Extraction

**File**: `app/routes/api.upload.ts` (lines 206-258)

**Library**: `epub2` (Node.js EPUB parser)

**Process**:

1. **Write temp file**
   - Save uploaded file to temporary directory
   - Required by `epub2` library

2. **Parse EPUB**
   - Use `EPub.createAsync(filePath)`
   - Library reads EPUB structure (ZIP format)

3. **Extract Chapters**
   - Iterate through `epub.flow` (ordered chapters)
   - Get chapter HTML content
   - Parse HTML to extract text

4. **Collect Metadata**
   - Title from EPUB manifest
   - Authors from metadata
   - Creation date from manifest

5. **Normalize Text**
   - Strip HTML tags
   - Collapse whitespace
   - Decode HTML entities

6. **Metadata Limit**
   - For author/metadata extraction: limit to first 2000 characters
   - Helps LLM-based metadata resolution be more efficient

7. **Cleanup**
   - Delete temporary file

**Output**:
```typescript
{
  text: string              // Combined chapter text
  metadata: {
    title?: string
    author?: string
    createdAt?: string
  }
}
```

### Web Article Extraction

**File**: `app/server/content-extractor.server.ts`

**Function**: `extractMainFromUrl(url: string)`

**Process**:

1. **Fetch HTML**
   - Use `fetch()` API
   - Follow redirects
   - Set user-agent header

2. **Parse HTML**
   - Use `jsdom` library
   - Create DOM from HTML string

3. **Extract Main Content**
   - Use Mozilla Readability library
   - Intelligently identifies article content
   - Removes navigation, sidebars, ads, etc.

4. **Collect Metadata**
   - Title from `<title>`, og:title, h1
   - Author from byline detection
   - Published date from meta tags
   - Description from meta tags

**Output**: `ExtractedContent`
```typescript
{
  title: string
  content: string           // HTML content
  textContent: string       // Cleaned text
  byline: string           // Author name
  publishedTime: string | null  // ISO date
  excerpt: string
}
```

**Function**: `extractMainFromHtml(html: string, url: string)`

- Same process but accepts pre-fetched HTML
- Used by web crawler

### Web Crawling

**File**: `app/server/crawler.server.ts`

**Function**: `crawlSite(startUrl: string, options: CrawlOptions)`

**Options**:
```typescript
{
  maxPages?: number        // Default: 50
  delay?: number          // Delay between requests (ms), default: 500
  onProgress?: (url) => void
}
```

**Process**:

1. **Initialize Queue**
   - Add start URL
   - Track visited URLs
   - Normalize URLs

2. **Process Queue**
   - Fetch page HTML
   - Extract content using `extractMainFromHtml()`
   - Discover links on page

3. **Filter Links**
   - Same host only (prevent crawling external sites)
   - Exclude file types: PDF, DOC, DOCX, XLS, PNG, JPG, GIF, etc.
   - Exclude common non-content paths
   - Normalize URL fragments and query params

4. **Rate Limiting**
   - Apply delay between requests (default 500ms)
   - Prevent overwhelming target server

5. **Return Results**
   - Array of `CrawledPage` objects

**Output**:
```typescript
CrawledPage {
  url: string
  title: string
  content: string         // HTML
  textContent: string
  publishedTime: string | null
}
```

**Error Handling**:
- Skip failed pages
- Continue crawling
- Return partial results

---

## Text Normalization & Chunking

### Metadata Extraction & Resolution

**File**: `app/server/document-metadata.server.ts`

**Function**: `resolveDocumentMetadata(metadata, content)`

**Features**:

1. **Automated Meta Tag Collection**
   - Author selectors: 23 different meta tag patterns
     - `meta[name="author"]`
     - `meta[name="article:author"]`
     - `link[rel="author"]`
     - etc.
   - Date selectors: 14 different patterns
     - `meta[property="article:published_time"]`
     - `meta[name="publish_date"]`
     - `time[datetime]`
     - etc.

2. **LLM-Based Inference** (optional)
   - Uses `gpt-4o-mini` for uncertain cases
   - Analyzes first 3 paragraphs
   - Normalizes dates to ISO 8601
   - Deduplicates authors

3. **Multi-Source Merging**
   - Combines: LLM results + byline + meta tags
   - Deduplicates author names
   - Sanitizes invalid authors
   - Prefers explicit meta tags over LLM

**Output**: `ResolvedMetadata`
```typescript
{
  authors: string[]           // Deduped author names
  publishedAt: string | null  // ISO 8601 date
  title: string | null
}
```

### Text Chunking

**File**: `app/server/document.server.ts`

**Function**: `chunkText(rawText: string)`

**Technology**: LangChain `RecursiveCharacterTextSplitter`

**Configuration**:
- Chunk size: 500 characters
- Overlap: 50 characters
- Recursively splits on: `["\n\n", "\n", " ", ""]`
  - Tries to split on paragraph breaks first
  - Falls back to sentences, then words, then characters
  - Preserves semantic boundaries

**Process**:

1. Take raw extracted text
2. Split using above configuration
3. Create `Document` objects from chunks
4. Preserve metadata in each chunk

**Output**: Array of `Document` objects
```typescript
{
  pageContent: string    // The chunk text
  metadata: {
    source?: string
    // Other metadata from original document
  }
}
```

**Example**:
```
Original text (2500 chars) →
Chunks: [500 chars, 500 chars, 500 chars, 500 chars, 500 chars, ...]
(each with 50-char overlap with previous)
```

---

## Embedding Generation

**File**: `app/server/document.server.ts`

**Function**: `generateEmbeddings(chunkTexts: string[])`

### AI Model

**Provider**: OpenAI
**Model**: `text-embedding-3-small`
**Dimensions**: 512 (optimized for storage and search)

### Process

1. **Batch Processing**
   - Accept array of chunk texts
   - Process in parallel batches
   - Max parallel calls: 100

2. **API Call**
   - Use Vercel `ai` SDK embeddings API
   - Returns embedding vector per chunk

3. **Output**
   - Array of 512-dimensional vectors
   - One per chunk in same order as input

### Cost & Performance

- `text-embedding-3-small`: ~$0.02 per 1M tokens
- Much cheaper than larger models
- Sufficient quality for semantic search
- 512 dimensions reduces storage vs. full 1536 dims

### Usage

```typescript
const chunks = [...];  // Array of chunk texts
const embeddings = await generateEmbeddings(chunks);
// embeddings[i] corresponds to chunks[i]
// Each embedding: number[] of length 512
```

---

## Storage Systems

### File Storage (Original Documents)

**Service**: Supabase Storage

**Configuration**:
- Bucket: `documents` (configured via `SUPABASE_BUCKET`)
- Region: Depends on Supabase project setup

**Upload Process**:

**File**: `app/server/supabase.server.ts`

```typescript
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE
);

// Upload file
await supabase.storage
  .from('documents')
  .upload(`${documentId}.${extension}`, fileBuffer, {
    contentType: 'application/pdf' | 'application/epub+zip',
    upsert: false
  });
```

**File Naming**:
- PDF: `{documentId}.pdf`
- EPUB: `{documentId}.epub`

**Content Types**:
- PDF: `application/pdf`
- EPUB: `application/epub+zip`

**Access Control**:
- Uses Supabase RLS (Row Level Security)
- Service role key used for uploads (server-side only)
- Authenticated users can download via signed URLs

### Vector Storage (Embeddings)

**Database**: PostgreSQL with `pgvector` extension

**Table**: `documentChunks`

**Vector Column**: `embedding` (vector(512))

**Semantic Search Query**:

**File**: `app/server/search.server.ts`

**Function**: `semanticSearch(userId, queryEmbedding, topK, documentIds?)`

```sql
SELECT
  dc.id,
  dc.text,
  dc.chunkIndex,
  d.id as documentId,
  d.title,
  d.url,
  d.publishedTime,
  1 - (dc.embedding <=> $1) as similarity
FROM documentChunks dc
JOIN document d ON dc.documentId = d.id
JOIN userDocument ud ON d.id = ud.documentId
WHERE ud.userId = $2
  AND (ARRAY[$3::text] IS NULL OR d.id = ANY($3))
ORDER BY dc.embedding <=> $1
LIMIT $4
```

**Key Features**:
- Uses PostgreSQL `<=>` operator (cosine distance)
- Similarity calculated as `1 - distance`
- Filters by user ownership via `userDocument` table
- Optional document ID filter
- Top K results via LIMIT

**Performance**:
- pgvector supports HNSW index for fast similarity search
- Index: `CREATE INDEX ON documentChunks USING hnsw (embedding vector_cosine_ops)`

### Metadata Storage

**Database**: PostgreSQL via Drizzle ORM

**Tables**:
- `document` - Document metadata
- `documentChunks` - Text chunks with embeddings
- `author` - Author records
- `documentAuthors` - M2M relationship
- `userDocument` - User-document access

---

## Database Schema

**File**: `app/db/schema.ts`

### Document Table

```typescript
documentTable = pgTable('document', {
  id: text('id').primaryKey(),
  url: text('url'),                        // Original URL or NULL for uploads
  title: text('title'),                    // Document title
  content: text('content'),                // Full HTML/original content
  textContent: text('textContent'),        // Full extracted text
  publishedTime: text('publishedTime'),    // ISO 8601 date
  createdAt: timestamp('createdAt', { withTimezone: true }),
  updatedAt: timestamp('updatedAt', { withTimezone: true })
});
```

### Document Chunks Table

```typescript
documentChunksTable = pgTable('documentChunks', {
  id: text('id').primaryKey(),
  documentId: text('documentId').references(() => documentTable.id),
  text: text('text'),                      // Chunk text (500 chars)
  chunkIndex: integer('chunkIndex'),       // 0-based chunk order
  embedding: vector('embedding', { dimensions: 512 }),  // pgvector
  createdAt: timestamp('createdAt', { withTimezone: true }),
  updatedAt: timestamp('updatedAt', { withTimezone: true })
});

// Index for semantic search
CREATE INDEX ON documentChunks
USING hnsw (embedding vector_cosine_ops);
```

### Author Tables

```typescript
authorTable = pgTable('author', {
  id: text('id').primaryKey(),
  name: text('name'),
  createdAt: timestamp('createdAt', { withTimezone: true }),
  updatedAt: timestamp('updatedAt', { withTimezone: true })
});

documentAuthorsTable = pgTable('documentAuthors', {
  id: text('id').primaryKey(),
  documentId: text('documentId').references(() => documentTable.id),
  authorId: text('authorId').references(() => authorTable.id),
  createdAt: timestamp('createdAt', { withTimezone: true }),
  updatedAt: timestamp('updatedAt', { withTimezone: true })
});
```

### Access Control Tables

```typescript
userDocumentTable = pgTable('userDocument', {
  id: text('id').primaryKey(),
  userId: text('userId'),
  documentId: text('documentId').references(() => documentTable.id),
  role: text('role'),                      // 'owner' or 'viewer'
  createdAt: timestamp('createdAt', { withTimezone: true }),
  updatedAt: timestamp('updatedAt', { withTimezone: true })
});

permissionTable = pgTable('permission', {
  id: text('id').primaryKey(),
  userId: text('userId'),
  resourceId: text('resourceId'),
  action: text('action'),                  // 'read', 'write', 'admin'
  createdAt: timestamp('createdAt', { withTimezone: true })
});
```

---

## API Endpoints

### File Upload Endpoint

**Route**: `POST /api/upload`

**Handler**: `app/routes/api.upload.ts` → `action()`

**Input**:
```
Content-Type: multipart/form-data
file: <binary file data>
```

**Process**:
1. Parse multipart form data
2. Get user from session
3. Check document allowance (Stripe tier)
4. Detect file type (PDF or EPUB)
5. Extract content and metadata
6. Generate chunks and embeddings
7. Save to database
8. Upload file to Supabase
9. Create author records

**Output**: Redirect to `/document/{documentId}`

**Errors**:
- 401: Not authenticated
- 402: Document limit reached (billing)
- 400: Invalid file type or corrupted file

### Web Import Endpoint

**Route**: `POST /document-create`

**Handler**: `app/routes/document-create.tsx` → `action()`

**Input**: Form data
```typescript
{
  url: string           // Required: URL to import
  crawl?: boolean       // Optional: crawl entire site
  maxPages?: number     // Optional: max pages to crawl (default: 50)
  splitMode?: boolean   // Optional: separate document per page
}
```

**Process**:

1. **Extract Content**
   - Fetch URL using `extractMainFromUrl()`
   - Extract title, content, metadata

2. **Optionally Crawl**
   - If `crawl: true`, use `crawlSite()`
   - Get all pages from domain

3. **Split or Aggregate**
   - `splitMode: true`: Create separate document per page
   - `splitMode: false`: Combine all text into one document

4. **For Each Document**:
   - Check if URL already imported
   - Resolve metadata (authors, date)
   - Generate chunks and embeddings
   - Save to database
   - Link to user

**Output**: Redirect to first document

**Errors**:
- 400: Invalid URL
- 402: Document limit reached
- 500: Content extraction failed

### Document Search Endpoint

**Route**: `GET /document-search?query=...`

**Handler**: `app/routes/document-search.tsx` → `loader()`

**Input**:
```
query: string    // Search query
topK?: number    // Number of results (default: 10)
documentIds?: string[]  // Filter to specific documents
```

**Process**:
1. Get user from session
2. Generate embedding for query using same model as documents
3. Run semantic search using `semanticSearch()`
4. Sort results by similarity score
5. Group by document
6. Render search results

**Output**: Search results with:
- Chunk text
- Document title and URL
- Similarity score (0-1)
- Chunk index

### Semantic Search API Endpoint

**Route**: `POST /api/document` (form action)

**Handler**: `app/routes/api.document.ts` → `action()`

**Input**: Form data
```typescript
{
  query: string
  topK?: number
}
```

**Output**: JSON response
```typescript
{
  results: SearchResult[]
}

SearchResult {
  chunkId: string
  chunkText: string
  chunkIndex: number
  documentId: string
  documentTitle: string
  documentUrl: string | null
  publishedTime: string | null
  similarity: number
}
```

---

## Complete Workflows

### PDF Upload Workflow

```
1. User selects PDF file via upload form
   ↓
2. POST /api/upload with multipart form data
   ↓
3. Server validates:
   - User authenticated
   - Document limit not exceeded
   - File is PDF (MIME type check)
   ↓
4. Extract text from PDF
   - Try pdf-parse
   - Fallback to pdfjs-dist
   - Normalize whitespace
   ↓
5. Extract metadata
   - Author, creation date from PDF
   ↓
6. Generate document ID (UUID)
   ↓
7. Resolve metadata using LLM if needed
   - Normalize author names
   - Convert dates to ISO 8601
   ↓
8. Chunk text
   - RecursiveCharacterTextSplitter
   - 500 chars, 50 char overlap
   ↓
9. Generate embeddings
   - OpenAI text-embedding-3-small
   - 512-dimensional vectors
   - Batch processing
   ↓
10. Save to database
    - Insert document record
    - Insert chunk records with embeddings
    - Create/link author records
    - Insert userDocument record
    ↓
11. Upload PDF to Supabase Storage
    - Filename: {documentId}.pdf
    - Content-Type: application/pdf
    ↓
12. Redirect to /document/{documentId}
```

### EPUB Upload Workflow

```
1. User selects EPUB file via upload form
   ↓
2. POST /api/upload with multipart form data
   ↓
3. Server validates same as PDF
   ↓
4. Extract EPUB chapters
   - Write temp file
   - Parse with epub2
   - Extract HTML from each chapter
   - Combine into single text
   - Normalize whitespace
   ↓
5. Extract metadata
   - Title, author from EPUB manifest
   ↓
6-12. Same as PDF workflow (UUID, metadata, chunking, embeddings, etc.)
```

### Web Article Import Workflow

```
1. User submits URL via /document-create form
   ↓
2. POST /document-create with form data (url, crawl?, maxPages?)
   ↓
3. Extract content from URL
   - Fetch HTML
   - Parse with jsdom
   - Extract article with Mozilla Readability
   - Get title, byline, publish date
   ↓
4. Check if URL already imported (avoid duplicates)
   ↓
5. If crawl: true
   - Crawl entire site with crawlSite()
   - Discover all links on domain
   - Extract content from each page
   - Apply delay between requests
   ↓
6. For each page/document
   - Resolve metadata (authors, dates)
   - If split mode: create separate document per page
   - If aggregate mode: combine all text
   ↓
7. Generate chunks and embeddings (same as PDF/EPUB)
   ↓
8. Save to database
   - No file upload (web articles only store text)
   ↓
9. Redirect to first imported document
```

### Semantic Search Workflow

```
1. User enters search query in document-search box
   ↓
2. GET /document-search?query=...
   ↓
3. Generate query embedding
   - Same model: text-embedding-3-small
   - Same dimensions: 512
   ↓
4. Run semantic search in PostgreSQL
   - Query embedding vs. chunk embeddings
   - Cosine similarity (1 - distance)
   - Filter by user (via userDocument table)
   - Order by similarity descending
   - Limit to topK results (default: 10)
   ↓
5. Process results
   - Group by document
   - Calculate document-level relevance
   - Aggregate similar chunks
   ↓
6. Render search results
   - Display chunk snippets
   - Show document title/URL
   - Display similarity score
   - Link to full document
```

---

## Dependencies & Configuration

### Core Libraries

#### Document Parsing

| Package | Version | Purpose |
|---------|---------|---------|
| `pdf-parse` | ^2.4.0 | Primary PDF text extraction |
| `pdfjs-dist` | ^5.4.296 | Fallback PDF extraction |
| `epub2` | ^3.0.2 | EPUB parsing and chapter extraction |

#### Web Content

| Package | Version | Purpose |
|---------|---------|---------|
| `jsdom` | ^27.0.0 | DOM implementation for HTML parsing |
| `@mozilla/readability` | ^0.6.0 | Intelligent article content extraction |

#### Text Processing & Chunking

| Package | Version | Purpose |
|---------|---------|---------|
| `langchain` | ^0.3.35 | Text splitting and document chains |
| `@langchain/core` | ^0.3.78 | LangChain core types |
| `marked` | ^16.3.0 | Markdown parsing |

#### AI & Embeddings

| Package | Version | Purpose |
|---------|---------|---------|
| `@ai-sdk/openai` | ^2.0.42 | OpenAI provider for Vercel AI SDK |
| `ai` | ^5.0.59 | Vercel AI SDK for embeddings |
| `openai` | ^6.1.0 | OpenAI client library |

#### Database & ORM

| Package | Version | Purpose |
|---------|---------|---------|
| `drizzle-orm` | ^0.44.5 | Type-safe ORM |
| `postgres` | ^3.4.7 | PostgreSQL client |
| `drizzle-kit` | ^0.31.5 | Drizzle migrations and CLI |

#### Cloud Storage

| Package | Version | Purpose |
|---------|---------|---------|
| `@supabase/supabase-js` | ^2.58.0 | Supabase client |
| `file-type` | ^21.0.0 | File type detection from buffer |

#### Framework

| Package | Version | Purpose |
|---------|---------|---------|
| `react` | ^19.1.1 | UI framework |
| `react-router` | ^7.9.2 | Routing |
| `tailwindcss` | ^4.1.13 | Styling |

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@host:port/dbname

# Supabase (file storage)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE=<service-role-key>
SUPABASE_BUCKET=documents

# OpenAI (embeddings)
OPENAI_API_KEY=sk-...

# Optional: Billing integration
STRIPE_SECRET_KEY=sk_...
```

### Database Setup

**Configuration File**: `drizzle.config.ts`

```typescript
export default defineConfig({
  schema: './app/db/schema.ts',
  out: './drizzle',
  dialect: 'postgresql',
  dbCredentials: {
    url: process.env.DATABASE_URL!
  }
});
```

**Initial Setup**:

```bash
# Install dependencies
npm install

# Generate initial schema
npx drizzle-kit generate

# Apply migrations
npx drizzle-kit migrate

# Or use custom migration script
node scripts/migrate.js
```

**Enable pgvector Extension**:

```sql
-- Run once in PostgreSQL database
CREATE EXTENSION IF NOT EXISTS vector;

-- Create HNSW index for fast similarity search
CREATE INDEX documentChunks_embedding_idx
ON documentChunks USING hnsw (embedding vector_cosine_ops);
```

### Supabase Storage Setup

```bash
# Create bucket via Supabase dashboard or API
# Bucket name: documents
# Make private (use signed URLs for access)
```

### RLS Policies (Supabase Storage)

```sql
-- Enable RLS on storage.objects
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to read their documents
CREATE POLICY "Users can read their own documents"
  ON storage.objects
  FOR SELECT
  USING (
    bucket_id = 'documents'
    AND auth.uid()::text = (storage.foldername(name))[1]
  );

-- Allow service role to write documents
CREATE POLICY "Service role can write documents"
  ON storage.objects
  FOR INSERT
  WITH CHECK (
    bucket_id = 'documents'
    AND auth.role() = 'service_role'
  );
```

---

## Implementation Checklist

- [ ] Set up PostgreSQL with pgvector extension
- [ ] Create Supabase project and storage bucket
- [ ] Configure RLS policies on storage
- [ ] Set up authentication (Clerk, Auth0, etc.)
- [ ] Create database schema using Drizzle
- [ ] Run migrations
- [ ] Implement PDF extractor with fallback
- [ ] Implement EPUB extractor
- [ ] Implement web content extractor with Readability
- [ ] Implement web crawler
- [ ] Implement text chunker (RecursiveCharacterTextSplitter)
- [ ] Implement metadata resolver with LLM
- [ ] Set up OpenAI embeddings integration
- [ ] Implement semantic search queries
- [ ] Build upload form component
- [ ] Build document view component
- [ ] Build search interface
- [ ] Implement billing/quota checks
- [ ] Add error handling and retry logic
- [ ] Test with various PDF/EPUB formats
- [ ] Test with various website structures
- [ ] Performance test with large documents
- [ ] Set up monitoring and logging

---

## Performance Considerations

### Chunking
- 500 characters captures ~150-200 words
- 50 character overlap maintains context between chunks
- For typical article (~5000 chars): ~10-12 chunks

### Embeddings
- `text-embedding-3-small`: ~5ms per request (Vercel AI)
- Batch 100 chunks: ~500ms total
- Cost: ~$0.02 per 1M tokens
- 512 dimensions: Good balance of quality vs. storage

### Vector Search
- HNSW index: O(log n) search complexity
- Typical query: <100ms for millions of vectors
- Cosine distance: Standard for text embeddings

### Storage
- Average PDF: 50-100 KB
- Average chunk: ~400 bytes
- 1000 documents × 10 chunks × 512 dims × 4 bytes = ~20 MB embeddings

---

## Error Handling Strategy

### PDF Extraction Failures
1. Primary: `pdf-parse`
2. Fallback: `pdfjs-dist`
3. Manual error class: `PdfExtractionError`
4. Retry: Up to 2 attempts

### EPUB Extraction Failures
1. Check file integrity
2. Validate EPUB structure
3. Return partial extraction if some chapters fail
4. Log specific chapter failures

### Web Extraction Failures
1. Network: Retry with exponential backoff
2. Parsing: Return raw text if Readability fails
3. Crawling: Skip failed pages, continue crawling
4. Metadata: Use defaults if extraction fails

### Embedding Generation Failures
1. OpenAI API errors: Retry with exponential backoff
2. Rate limits: Queue and process asynchronously
3. Invalid text: Skip chunk, continue
4. Fallback: Use zero vector if all else fails

### Database Errors
1. Connection: Retry with pool management
2. Constraint violations: Log and skip
3. Transactions: Rollback and retry
4. Vector operations: Ensure pgvector installed

---

## Security Considerations

### File Upload
- Validate file type via MIME detection
- Scan for malicious content (optional: VirusTotal API)
- Store in private bucket with RLS policies
- Limit file size to prevent DoS

### Web Crawling
- Respect robots.txt
- Limit concurrent requests
- User-agent header
- Timeout on unresponsive servers

### Embeddings
- OpenAI API key in environment only
- No sensitive data in chunk text
- Rate limiting on API

### Database
- Use parameterized queries (Drizzle ORM handles this)
- RLS policies on sensitive tables
- Encryption at rest (Supabase default)
- Audit logging for document access

### Access Control
- User must own document to search
- Shared documents filtered by `userDocument` table
- Service role key for server-side operations only
- Row-level security on all tables

---

## Testing Strategy

### Unit Tests
- PDF extraction (valid, corrupted, edge cases)
- EPUB extraction (various EPUB versions)
- Text chunking (various text lengths)
- Metadata extraction (various patterns)
- Web extraction (various article formats)

### Integration Tests
- Full upload workflow (PDF → chunks → embeddings → database)
- Full web import workflow
- Semantic search accuracy
- Crawling (single vs. multi-page)
- Metadata resolution with LLM

### Performance Tests
- Large PDF (100+ MB) extraction
- Large crawl (100+ pages)
- Bulk embedding generation (10,000+ chunks)
- Search latency under load

### Security Tests
- File type validation
- SQL injection prevention
- XSS prevention in rendered content
- RLS policy enforcement

---

## Scaling Considerations

### Horizontal Scaling
- Offload embedding generation to async queue (Bull, RabbitMQ)
- Process crawls in background workers
- Distribute document processing across workers

### Optimization
- Cache embeddings for repeated queries
- Pre-compute common searches
- Use connection pooling for database
- CDN for document delivery

### Monitoring
- Track extraction success rates
- Monitor embedding generation latency
- Alert on failed documents
- Log search queries for analytics

---

## References

- [PDF-Parse Documentation](https://github.com/modesty/pdf-parse)
- [PDF.js Documentation](https://mozilla.github.io/pdf.js/)
- [EPUB2 Library](https://github.com/troyeguo/epub2)
- [Mozilla Readability](https://github.com/mozilla/readability)
- [Vercel AI SDK](https://sdk.vercel.ai/)
- [LangChain Text Splitting](https://js.langchain.com/docs/modules/data_connection/document_loaders/how_to/recursive_character_text_splitter)
- [PostgreSQL pgvector](https://github.com/pgvector/pgvector)
- [Drizzle ORM](https://orm.drizzle.team/)
- [Supabase Storage](https://supabase.com/docs/guides/storage)
