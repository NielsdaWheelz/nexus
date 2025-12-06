# Nexus Subsystem Spec: Jobs & Observability

## 1. Scope
- Owns global conventions for Celery jobs: naming, payload shape, idempotency guards, retry/backoff defaults, and dead-letter handling (logical, not a persisted job table in v1).
- Cross-cutting job behavior for:
  - Ingestion: fetch/extract text, populate canonical fields, set `processing_status` transitions.
  - Chunking/embedding: create/delete `Chunk` rows and embeddings per `(media_id, chunking_strategy)`.
  - Search indexing: covered by chunking/embedding; no separate indexer beyond these tasks unless reindex is requested.
  - LLM: **v1 calls are synchronous per conversations spec; no background LLM jobs.**
  - Billing/Stripe: webhook processing handled synchronously in-request; future job wrapper only if needed.
- Observability conventions for all jobs: structured logs, metrics, traces/spans.
- Explicitly does **not** redefine business logic from other specs (ingestion failure reasons, chunking semantics, visibility rules, billing tier rules, LLM prompt behavior).
- Does not add new public HTTP APIs beyond optional minimal admin/debug endpoints (none in v1).

## 2. Dependencies
- Domain entities touched by jobs (read/write/observe):
  - `Media` (read+write `processing_status`, `failure_reason`, canonical fields).
  - `Chunk` (write lifecycle).
  - `Subscription`, `UsageRecord` (read/write inside billing webhook processing).
  - `Conversation`, `Message`, `MessageContext` (observe only; no async LLM work in v1).
- `Library`, `LibraryUser` (observe only for trace/log labels; jobs never read or mutate libraries or `LibraryMedia`).
- Specs relied on:
  - `spec-ingestion.md` (media lifecycle, failure_reason enum, retry semantics).
  - `spec-chunking-search-index.md` (chunk/embedding tasks, search availability).
  - `spec-conversations-llm.md` (LLM synchronous decision; usage increment contract).
  - `spec-billing-subscriptions-usage.md` (Stripe webhook handling, quota enforcement).
  - `spec-libraries-permissions-visibility.md` (visibility rule referenced in traces/log labels only).
  - `domain-model.md` (entity invariants, processing_status lifecycle).
- External services: Celery + Redis (broker/backend), PostgreSQL + pgvector (storage/index), Supabase storage, Stripe (webhooks), embedding API, HTTP fetchers, LLM provider (sync only), tracing/metrics backend (implementation-defined).

## 3. Responsibilities
- Must:
  - Enforce dotted job naming convention: `nexus.{subsystem}.{verb}` (e.g., `nexus.ingest.process_media`, `nexus.ingest.chunk_media`, `nexus.ingest.embed_chunks`, `nexus.billing.process_stripe_event`).
  - Standardize payload shape: JSON-serializable dict with `job_id` (uuid), `trigger` (source endpoint/event), primary identifiers (`media_id`, `chunking_strategy`, `stripe_event_id`, etc.), and optional `actor_user_id` when an action is user-initiated.
  - Define idempotency per job type (row locks and state checks) and permitted DB mutations.
  - Define retry/backoff defaults per family (ingest/chunk/embed vs Stripe).
  - Specify when jobs are enqueued (which HTTP endpoints or internal events).
  - Ensure job side effects honor existing invariants (processing_status transitions, chunk atomicity, Stripe event idempotency).
  - Define observability (logs/metrics/traces) emitted by each job.
- Must not:
  - Invent new enums, states, or visibility rules.
  - Bypass authorization/visibility helpers.
  - Create new entities/tables; rely on existing domain model and task queues.

## 4. External Interfaces

### 4.1 Job Conventions (all jobs)
- Naming: `nexus.{subsystem}.{verb}`; optional suffix for scope (e.g., `.reindex_media`).
- Payload (JSON):
  - `job_id: uuid` (generated at enqueue time, passed through retries).
  - `trigger: string` (e.g., `http:POST /api/v1/media/upload-url`, `webhook:stripe`).
  - Domain identifiers (per job below).
  - `actor_user_id: uuid | null` when initiated by a user action (observability only; jobs MUST NOT perform authorization based on it).
  - `attempt: int` is implicit from Celery retry count; not stored in payload.
- Idempotency guard pattern: first statement inside job performs authoritative state check (e.g., `SELECT FOR UPDATE` on media row with expected status) and aborts silently if already processed.
- Retry/backoff defaults unless overridden: exponential backoff with jitter, base 2s, max 3 attempts for infra errors; domain errors set terminal state and do not re-raise for Celery retry.
- Dead-letter: after max retries, job finishes by writing domain failure (if applicable) and emits error log/metric; no persisted job table in v1.

### 4.1.1 Ingestion: `nexus.ingest.process_media` (wraps `extract_media_task`)
- Triggered by: `POST /api/v1/media/upload-url`, `POST /api/v1/media/upload-file`, `POST /api/v1/media/{id}/retry`.
- Payload: `{ job_id, trigger, actor_user_id, media_id }`.
- Idempotency: row lock on `media` expecting `processing_status='pending'`; abort if not pending.
- Side effects:
  - `processing_status: pending → processing → ready_for_reading` (or `failed` with `failure_reason` enum).
  - Populate `plain_text`, `html`, `title`; insert authors/media_authors (insert-only) using upsert/`ON CONFLICT DO NOTHING` for idempotency.
  - Enqueue chunk job if `plain_text` non-empty.
- Retry/backoff: infra errors (broker/network/storage transient) → Celery retries up to 3 with exponential backoff; domain errors (parse/extraction/validation) set `failed` and do not retry automatically.
- Failure writes: `failure_reason ∈ {fetch_error, parse_error, extraction_error, storage_error}`; `processing_completed_at` set on failure.

### 4.1.2 Chunking: `nexus.ingest.chunk_media`
- Triggered by: completion of `process_media` when `plain_text` non-empty (or manual re-chunk).
- Payload: `{ job_id, trigger, media_id, chunking_strategy }` where `chunking_strategy` comes from configured default per chunking spec.
- Idempotency/guard: allowed when `plain_text` non-empty AND `processing_status IN ('ready_for_reading','indexed')`; delete-then-insert chunks inside a transaction to maintain all-or-nothing.
- Side effects: create chunk rows `(media_id, chunking_strategy, sequence_index, content, embedding=NULL)`; enqueue embed job.
- Retry/backoff: infra errors retried (max 3); domain errors set `processing_status='failed'`, `failure_reason='chunk_error'`.

### 4.1.3 Embedding: `nexus.ingest.embed_chunks`
- Triggered by: completion of `chunk_media`.
- Payload: `{ job_id, trigger, media_id, chunking_strategy }`.
- Idempotency: skips if no chunks with `embedding IS NULL`; per-batch updates allow safe retry.
- Side effects: write embeddings in batches; upon completion set `media.processing_status='indexed'` and `processing_completed_at`.
- Retry/backoff: infra errors retried (max 3); domain/model/validation errors set `processing_status='failed'`, `failure_reason='embed_error'` and delete chunks for the strategy.

### 4.1.4 Search Reindex (future)
- `nexus.search.reindex_media` is **out of scope for v1**. Future maintenance job to (re)chunk/embed for new strategies; not implemented in MVP.

### 4.1.5 Billing/Stripe: `nexus.billing.process_stripe_event`
- Triggered by: `POST /api/v1/webhooks/stripe`.
- v1 handling: process synchronously in the webhook handler (no Celery). Stripe’s own retries provide delivery guarantees.
- Payload (if queued in a future version): `{ job_id, trigger: "webhook:stripe", stripe_event_id, stripe_event_type, user_id, raw_event_ptr }`.
- Idempotency: check `stripe_event_id` replay table; no-op if already processed.
- Side effects: apply subscription status/tier updates per billing spec; may write `Subscription`, `User.subscription_tier`, period fields.
- Retry/backoff: in-request handling only; failures logged; rely on Stripe retry. If queued later: modest retries (cap 5); 4xx/invalid payload → no retry.

### 4.2 Admin/Debug Endpoints
- v1: none. Operational visibility is via logs/metrics/traces. Manual retries use existing ingestion `/retry` endpoint.

## 5. State & Lifecycles
- Job lifecycle (Celery): queued → running → succeeded | failed (retriable) → exhausted (dead-letter equivalent). Persistence is in Celery backend; no `job_run` table in v1.
- Domain lifecycles tied to jobs:
  - `process_media` success ⇒ `Media` moves `pending → processing → ready_for_reading`; authors inserted; chunk job enqueued if `plain_text` present.
  - `chunk_media` success ⇒ chunks exist for `(media, strategy)`; embed job enqueued. Allowed even if `processing_status='indexed'` for new strategies.
  - `embed_chunks` success ⇒ all embeddings populated; `Media.processing_status='indexed'`, `processing_completed_at` set.
  - Any failure in extraction/chunk/embed ⇒ `processing_status='failed'`, `failure_reason` set; retry endpoint resets to `pending`, clears `failure_reason`, deletes chunks/embeddings, and re-runs the full pipeline (including extraction).
  - `process_stripe_event` success ⇒ subscription/tier state consistent with Stripe event; failure with no retries left must be surfaced via logs/metrics for manual intervention.
- Representation: statuses live in domain tables (Media, Subscription). Celery result backend holds task status only; not user-facing.

## 6. Invariants
- For each `(media_id, chunking_strategy)`, after job completion either zero chunks exist or a complete, gap-free set exists; no partial sets persist across job boundaries.
- `Media.plain_text` must be non-empty before transitioning to `ready_for_reading` for HTML/EPUB. For PDF: if `plain_text` is non-empty, it is highlightable/chunkable like HTML/EPUB; if `plain_text` is empty (scanned/failed), skip chunking/embedding, stay `ready_for_reading`, readable-only (no highlighting/search), and surface this clearly in UI.
- Failed status in v1 means the media is not readable/trusted; UI should block reading until retried or deleted.
- Retries of `process_media`, `chunk_media`, or `embed_chunks` are safe and must not duplicate authors or chunks (chunking uses delete-then-insert transaction; author/media_author inserts use upsert/ON CONFLICT DO NOTHING).
- `Media.processing_status='indexed'` only when every chunk for the strategy has non-null embeddings.
- Stripe event handling is idempotent per `stripe_event_id`; a single event may only update subscription state once.
- Async LLM work is out of scope for v1.

## 7. Error Handling
- Categories:
  - Transient infra (broker disconnect, storage/network timeout, DB deadlock): Celery retry with exponential backoff; log `warning`, include `will_retry=true`.
  - Permanent content errors (corrupt PDF/EPUB, unsupported format, empty HTML text, invalid chunking_strategy, storage read errors): set `processing_status='failed'` with string codes (`fetch_error`, `parse_error`, `extraction_error`, `storage_error`, `chunk_error`, `embed_error`); log `error`, no retry. `indexing_failed` is a UI label only, not a DB literal.
  - Misconfiguration (unknown `media_id`, unknown strategy): abort with log `error`, no retry; do not write state.
  - Stripe 4xx (invalid signature/body, unknown price_id): no retry; log with `error_code`.
- When to mark `Media.processing_status='failed'`:
  - Extraction fails validation or content processing.
  - Chunking/embedding domain failure.
  - After infra retries exhausted for ingest/chunk/embed.
- User surface (per PRD/ingestion spec): failures expose `failure_reason`; retry endpoint clears status and re-enqueues.

## 8. Performance, Limits, Backoff (guidance)
- Concurrency guidance (non-binding): dedicate Celery queues per family (`ingest`, `chunk`, `embed`); cap ingest/embedding workers to avoid overload on embedding API; enable visibility timeout and jittered retries to prevent thundering herd.
- Retry/backoff defaults:
  - Ingest/chunk/embed: max 3 infra retries, exponential backoff base 2s with jitter; hard timeouts per stage (per ingestion spec) to avoid hung tasks.
  - Stripe: handled synchronously in-request; no Celery retries in v1.
- Safeguards:
  - Skip chunk/enqueue when `plain_text` empty to avoid useless work.
  - Embedding batch size 100; throttle/backoff on 429 from provider.
  - Manual retry endpoint allowed only from `failed` state; cleans chunks/embeddings first.

## 9. Observability

### 9.1 Logs
- Structured log fields (JSON): `event`, `level`, `job_name`, `job_id`, `media_id?`, `user_id?`, `stripe_event_id?`, `processing_status_before`, `processing_status_after`, `failure_reason?`, `retries_remaining`, `duration_ms`, `plain_text_length?`, `chunking_strategy?`.
- Levels:
  - info: job start, completion, state transitions.
  - warning: transient failure with retry scheduled.
  - error: permanent failure, retries exhausted, or invalid payload.

### 9.2 Metrics
- Must-have for v1 (minimal):
  - `nexus_jobs_started{job_name}`
  - `nexus_jobs_failed{job_name,reason}`
  - `nexus_jobs_duration_ms{job_name}` (histogram)
  - `nexus_billing_webhook_failed{event_type,reason}` only if/when webhooks are queued
- Nice-to-have/backlog: per-strategy chunk metrics, queue depth gauges, LLM placeholders.
- UI observability in shell spec is separate; this section covers backend jobs only.

### 9.3 Traces
- Each job execution emits a span named `job:{job_name}` with tags: `job_id`, `job_name`, `media_id`, `user_id` (if known), `retry_count`, `failure_reason?`.
- Child spans for external calls: `http.fetch`, `storage.read`, `embedding.call`, `stripe.call`, `db.transaction`.
- Trace sampling configurable; default on for errors and slow jobs (>P95 duration).

## 10. Test Matrix
- Ingestion happy path: media upload → ingest job runs once, status `pending→processing→ready_for_reading` (and `indexed` if chunk/embed succeeds), logs/metrics emitted.
- Ingestion transient error: first attempt fails (network), retried, succeeds; logs contain retry and success; metrics increment started/failed/succeeded appropriately.
- Ingestion permanent error: parse failure → status `failed`, `failure_reason` set; retry endpoint resets to `pending` and enqueues new job.
- Chunking idempotency: run `chunk_media` twice; ensure no duplicate chunks and atomic delete-then-insert behavior.
- Embedding failure: embedding API 500 triggers retry; after exhaustion, status `failed`, chunks cleaned; retry resets to pending and re-runs full pipeline.
- Search reindex: **omitted in v1**; no tests required.
- Billing: webhook event processed once; replayed event is ignored; Stripe 5xx retry works; invalid event does not retry but logs failure.
- Observability: unit/integration assertions that each job emits start/finish logs and increments counters; histogram buckets receive duration samples.

## 11. Open Questions
- Do we need a persisted `job_run` table for audit/replay, or are Celery backend + domain states sufficient for v1?
- Should we introduce a dedicated dead-letter queue for ingest/chunk/embed after retries exhaust, to allow manual drain?
- Where are metrics/logs/traces shipped (self-hosted vs managed service) and what retention/SLOs apply?
- Failure_reason alignment across specs: ensure ingestion spec uses the fixed set (`fetch_error`, `parse_error`, `extraction_error`, `storage_error`, `chunk_error`, `embed_error`); `indexing_failed` remains UI-only.

## 12. Future Extensions
- Per-user rate limiting for ingestion/conversation-triggered jobs to prevent abuse.
- Finer-grained job types (page-level PDF processing, per-strategy reindex) with targeted retries.
- Async LLM job family with per-model cost/latency metrics and deduplication of assistant messages.
- Automated reindex/rechunk on strategy/model upgrades with migration guards.

