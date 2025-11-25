# Job Orchestration & State Machines (Celery)

## 1. Celery Configuration

### 1.1 Broker & Framework

- **Framework**: Celery (Python async task queue)
- **Broker**: Redis (message queue)
- **Result Backend**: Redis (store job results)
- **Serializer**: JSON (for transparency and debugging)

### 1.2 Named Queues

```python
CELERY_TASK_ROUTES = {
    'tasks.ingest_document': {'queue': 'ingestion', 'routing_key': 'ingestion'},
    'tasks.canonicalize_document': {'queue': 'ingestion', 'routing_key': 'ingestion'},
    'tasks.chunk_and_embed_document': {'queue': 'embedding', 'routing_key': 'embedding'},
    'tasks.embed_thought_source': {'queue': 'embedding', 'routing_key': 'embedding'},
    'tasks.remap_highlights': {'queue': 'remap', 'routing_key': 'remap'},
    'tasks.update_conversation_summary': {'queue': 'conversation', 'routing_key': 'conversation'},
}

CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_DEFAULT_ROUTING_KEY = 'default'
```

### 1.3 Concurrency & Prefetch

```python
# Default concurrency per queue
# Run with: celery -A app worker -l info -Q ingestion -c 2
# or configure via environment variables

CELERY_WORKER_CONCURRENCY = {
    'ingestion': 2,        # 2 concurrent ingestion tasks
    'embedding': 2,        # 2 concurrent embedding tasks
    'remap': 1,           # 1 concurrent remap (sequential)
    'conversation': 1,    # 1 concurrent conversation/summary
}

# Prefetch (tasks fetched from queue but not yet running)
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Strict: one task at a time per worker
```

### 1.4 Worker Configuration

**Single worker process, multiple concurrency**:

```bash
# Recommended Phase 1 setup
celery -A app worker \
  -l info \
  --concurrency=4 \
  --queues=ingestion,embedding,remap,conversation \
  --prefetch-multiplier=1
```

**Per-queue workers (optional future setup)**:

```bash
# Ingestion worker (concurrency=2)
celery -A app worker -l info -Q ingestion -c 2

# Embedding worker (concurrency=2)
celery -A app worker -l info -Q embedding -c 2

# Remap worker (concurrency=1)
celery -A app worker -l info -Q remap -c 1

# Conversation worker (concurrency=1)
celery -A app worker -l info -Q conversation -c 1
```

**Environment variable configuration**:

```bash
# Set concurrency via environment
export CELERY_INGESTION_CONCURRENCY=2
export CELERY_EMBEDDING_CONCURRENCY=2
export CELERY_REMAP_CONCURRENCY=1
export CELERY_CONVERSATION_CONCURRENCY=1
```

### 1.5 Hard Limits & Timeouts

**PDF extraction constraints**:

- **Max PDF size**: 50 MB
- **Max PDF pages**: 2500 pages
- **Extraction timeout**: ~30 seconds (soft limit, may extend for very large documents)

**Validation**:

```python
MAX_PDF_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_PDF_PAGES = 2500
EXTRACTION_TIMEOUT = 30  # seconds

def ingest_document(document_id: UUID):
    blob = download_from_s3(...)
    if len(blob) > MAX_PDF_SIZE:
        raise ValidationError(f'PDF exceeds max size ({MAX_PDF_SIZE})')

    doc_info = extract_pdf_info(blob)
    if doc_info['page_count'] > MAX_PDF_PAGES:
        raise ValidationError(f'PDF exceeds max pages ({MAX_PDF_PAGES})')
```

**Error handling**:

- Files exceeding limits fail immediately with `ERR_PDF_TOO_LARGE` or `ERR_PDF_TOO_COMPLEX`
- No retry is attempted
- User sees error: "File too large or complex. Maximum 50 MB, 2500 pages."

---

## 2. Phase 1 Job Specifications

See [spec/ingestion.md](ingestion.md) for detailed job specs:

- `ingest_document`: Download, hash
- `canonicalize_document`: Extract canonical text, structure
- `chunk_and_embed_document`: Chunking, embedding
- `remap_highlights`: Highlight remapping on version change
- `embed_thought_source`: Embedding for annotations/messages
- `update_conversation_summary`: LLM-based summarization

All jobs include:
- **Idempotency key**: Deterministic hash to skip re-runs
- **Retry policy**: Max attempts, exponential backoff
- **Concurrency control**: Row-level locks where needed
- **Error handling**: Transient vs permanent errors

---

## 3. Idempotency & Deduplication

All jobs are **idempotent**: running with same inputs multiple times produces same result.

**Idempotency key**:

```python
def compute_idempotency_key(task_name, task_data):
    """Generate deterministic key for task."""
    key_components = [task_name]

    # Task-specific key fields
    if task_name == 'canonicalize_document':
        key_components.extend([
            task_data['document_id'],
            task_data['content_hash'],
            EXTRACTOR_VERSION
        ])
    elif task_name == 'chunk_and_embed_document':
        key_components.extend([
            task_data['document_id'],
            task_data['chunk_version'],
            task_data['embedding_model']
        ])

    return hashlib.sha256(':'.join(key_components).encode()).hexdigest()
```

**Before starting job**: Check if result already exists for this idempotency key. If so, return cached result.

---

## 4. Retry Policies

Job-specific retry configurations:

| Job | Max Attempts | Backoff Strategy | Permanent Errors |
|-----|--------------|------------------|------------------|
| `ingest_document` | 3 | 1m, 5m, 15m | 404, 401 |
| `canonicalize_document` | 5 | 1m, 2m, 4m, 8m, 16m | Unknown format, no text layer |
| `chunk_and_embed_document` | 5 | 2m, 4m, 8m, 16m, 32m | 401 (API key) |
| `remap_highlights` | 3 | 1m, 5m, 15m | None (partial success okay) |
| `embed_thought_source` | 5 | 1m, 2m, 4m, 8m, 16m | 401 (API key) |
| `update_conversation_summary` | 3 | 5m, 15m, 30m | 401 (API key) |

**Exponential backoff with jitter** to avoid thundering herd.

---

## 5. Dead-Letter Queue (DLQ)

After max retries, job moves to DLQ:

```python
async def on_job_failed(job):
    if job.attemptsMade >= job.opts.maxAttempts:
        await deadLetterQueue.add({
            'original_job': job.toJSON(),
            'failure_reason': job.failedReason,
            'attempts': job.attemptsMade,
            'failed_at': datetime.now()
        })
```

**DLQ retention**: 90 days

**Admin review**: Daily digest email if DLQ > 100 items

**Manual retry**:

```python
async def retryDLQJob(dlqJobId):
    dlqJob = await deadLetterQueue.getJob(dlqJobId)
    originalJob = dlqJob.data.original_job

    # Re-enqueue with reset retry count
    await originalQueue.add(
        originalJob.name,
        originalJob.data,
        { attempts: 0 }
    )

    await dlqJob.remove()
```

---

## 6. State Machines

### 6.1 Document Ingestion State Machine

**States**: `pending` → `processing` → `ready` / `failed`

| State | Status | Jobs Enqueued | User Sees |
|-------|--------|---------------|-----------|
| pending | Awaiting ingest | None | "Processing..." |
| processing | Extraction running | canonicalize_document, chunk_and_embed, remap (if version change) | "Processing..." |
| ready | Complete | None | Document readable + searchable (once embedding_status=ready) |
| failed | Max retries exceeded | None | Error banner with retry button |

**Transitions**:

```
[create] → pending
pending → processing (ingest_document dequeued)
processing → ready (canonicalize_document success)
processing → failed (canonicalize_document max retries exceeded)
failed → pending (user clicks retry or admin requeues)
ready → processing (admin re-extracts)
```

### 6.2 Embedding State Machine

**States**: `pending` → `ready` / `failed`

Orthogonal to document status (document can be `ready` while embedding is `failed`).

| State | User Sees |
|-------|-----------|
| pending | "Indexing for search..." |
| ready | No message (search works) |
| failed | "Search unavailable for this document" |

### 6.3 Highlight Remapping State Machine

**States** (implicit, no enum):

- **valid**: `is_detached=false`, version matches current
- **stale**: Version mismatch, remap pending
- **detached**: `is_detached=true`, text not found
- **hidden**: `is_hidden=true`

| State | Rendering |
|-------|-----------|
| valid | Inline highlight with color |
| stale | Dimmed inline, "Updating..." tooltip |
| detached | Separate "Orphaned Highlights" section |
| hidden | Not rendered, retrievable via filter |

---

## 7. Job Cancellation

Jobs MAY be cancelled if:

- User deletes media object mid-pipeline
- Admin manually cancels job

**Cancellation behavior**:

```python
async def cancelJob(jobId):
    job = await jobQueue.getJob(jobId)

    if not job:
        raise Exception('Job not found')

    if job.state == 'completed':
        return { 'cancelled': False, 'reason': 'already_completed' }

    if job.state == 'active':
        await job.abort()  # Worker must check for abort signal
    else:
        await job.remove()  # Remove from queue

    return { 'cancelled': True }
```

**Worker abort handling**: All workers must check for cancellation periodically.

---

## 8. Concurrency & Locking

**Row-level locks** for concurrent operations:

```sql
SELECT * FROM highlights
WHERE media_type = :media_type AND media_id = :media_id
  AND (canonical_version = :old_version OR transcript_hash = :old_version)
FOR UPDATE
```

Ensures atomic updates when remapping.

---

## 9. Logging & Observability

**Per-job logging**:

```python
@app.task(bind=True)
def canonicalize_document(self, document_id):
    logger.info(f'Task {self.request.id} started: canonicalize_document({document_id})')

    try:
        # ... work ...
        logger.info(f'Task {self.request.id} completed')
        return {'status': 'success'}
    except Exception as e:
        logger.error(f'Task {self.request.id} failed: {e}')
        raise
```

**Metrics tracked**:

- Job count by type, state, queue
- Job latency (p50, p95, p99)
- Retry count distribution
- DLQ size, error codes

