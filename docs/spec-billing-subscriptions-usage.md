# Nexus Subsystem Spec: Billing, Subscriptions & Usage

## 1. scope
- Defines subscription tiers/limits, enforcement rules for media-count and LLM usage, subscription lifecycle synced with Stripe, and the minimal HTTP/webhook/internal contracts other subsystems call.
- Out of scope: coupons, seats, org-level billing, per-token metering, prepaid credits, taxes/receipts UX, multi-tenant orgs.

## 2. dependencies
- Stripe (Checkout, Billing Portal, subscription webhooks).
- Persistence: `User`, `Subscription`, `UsageRecord`, `Library`, `LibraryMedia`.
- Upstream subsystems that call this spec: conversations/LLM (quota checks), ingestion/libraries (media add), auth/accounts (surface tier/status).
- Time source: UTC date boundaries only.

## 3. responsibilities
- Own canonical mapping from `subscription_tier` → limits/behaviors.
- Enforce LLM daily usage limits.
- Enforce default-library media-count limits.
- Keep `User.subscription_tier` consistent with Stripe subscription status (no grace in v1).
- Provide HTTP APIs for account/billing UX and Stripe webhook ingestion.
- Provide internal helper contracts for other subsystems.
- Conversations/LLM subsystem must delegate quota changes to this spec; it must not mutate `UsageRecord` directly.

## 4. external interfaces

### 4.1 HTTP (authenticated user scope)
- `GET /api/v1/account/billing/overview`
  - Returns: `subscription_tier`, `billing_state` (normalized: none | active | past_due | canceled | unpaid | incomplete), media_limit (tier-based), media_count_default, llm_daily_limit, llm_used_today, llm_remaining_today, stripe_portal_available (bool).
  - Raw Stripe status is not exposed to clients.
  - Errors: `BILLING_TIER_CONFLICT` (409), generic 500.
- `POST /api/v1/account/billing/checkout-session`
  - Body: `{ target_tier: "personal" }` (pro deferred to future extension)
  - Action: create Stripe Checkout session for upgrade/new subscription; returns `{ checkout_url }`.
  - Errors: `BILLING_SUBSCRIPTION_REQUIRED` (403/402 when trying to “upgrade” from delinquent/not-active without resolving), `STRIPE_SESSION_CREATION_FAILED` (502), `BILLING_TIER_CONFLICT` (409).
- `POST /api/v1/account/billing/portal-session`
  - Action: create Stripe Billing Portal session; returns `{ portal_url }`.
  - Errors: `BILLING_NO_CUSTOMER` (403 if no stripe_customer_id), `STRIPE_SESSION_CREATION_FAILED` (502).

### 4.2 Webhook
- `POST /api/v1/webhooks/stripe`
  - Accepts Stripe events. Required types (v1 minimal):
    - `customer.subscription.created`
    - `customer.subscription.updated`
    - `customer.subscription.deleted`
  - Behavior: validate signature, enforce idempotency (event_id replay check), map event → Subscription.status + period fields + `user.subscription_tier`.
  - Errors: `STRIPE_WEBHOOK_INVALID` (400), `STRIPE_WEBHOOK_REPLAY` (409), 500 on unexpected.

### 4.3 Internal helper APIs (conceptual contracts)
- Pure helpers: return structs; they do not throw/raise subsystem error codes. HTTP/service layers map `allowed=false` to error codes.
- `enforce_media_limit(user_id) -> {allowed: bool, limit: int, count: int, remaining: int}`
  - Called by ingestion/library writes before adding to default library.
  - Callers map `allowed=false` → `LIMIT_MEDIA_DEFAULT_EXCEEDED` (403).
- `check_and_maybe_increment_llm_usage(user_id, cost=1) -> {allowed: bool, remaining: int, limit: int, error_code?: "LLM_QUOTA_EXCEEDED"}`
  - If over/at limit: `allowed=false`, `remaining=0`, `error_code="LLM_QUOTA_EXCEEDED"`; MUST NOT increment.
  - If allowed: atomically upsert/increment UsageRecord for today (UTC) and return updated remaining.
- `compute_current_usage(user_id) -> {media_count_default: int, llm_used_today: int, tier: subscription_tier, limits: {...}}`
- `apply_subscription_status(user_id, stripe_subscription_id, status, price_id, period_start, period_end, cancel_at_period_end)` used only by webhook/Stripe flows; encapsulates tier mapping (no grace in v1).

## 5. state & lifecycles

### 5.1 Tier & limits (v1)
| subscription_tier | max media in default | daily LLM limit | over-limit behavior |
| --- | --- | --- | --- |
| free | 5 | 10 | media: reject new adds; LLM: reject with quota error |
| personal | unlimited | 50 | media: allowed; LLM: reject after 50/day |
| pro (future) | unlimited | 100 (placeholder) | media: allowed; LLM: reject after 100/day (pro not in v1 checkout) |

Notes:
- Media limit enforced only on default library additions (since all media must reside there).
- LLM limit counts user messages that trigger an LLM call; assistant messages never count.

### 5.2 UsageRecord day semantics
- date is UTC (YYYY-MM-DD). One row per (user_id, date).
- New UTC date ⇒ new record; no batch job required.
- Counter increments only when an LLM call is actually made (post-quota check).

### 5.3 Subscription lifecycle and tier mapping
- Stripe `Subscription.status` states considered: `incomplete`, `active`, `past_due`, `unpaid`, `canceled`.
- Entitlements: only `active` is treated as paid; any non-`active` status downgrades to `free` immediately (no grace in v1).
- Free-tier users may have zero Subscription rows; paid tiers require exactly one active-ish row.
- Mapping to `User.subscription_tier`:
  - `active` + price_id→personal → tier=personal.
  - `active` + price_id→pro → tier=pro (pro not exposed in v1 checkout; reserved).
  - Any non-`active` status (or unknown price_id) → tier=free.
- Price→tier mapping source of truth: configured mapping `stripe_price_id -> subscription_tier` (env/config table). Unknown price_id must be rejected (log, leave tier unchanged, mark Subscription for manual review).
- Only one active-ish Subscription per user (statuses in {active, past_due, unpaid, incomplete}); new Checkout must cancel/replace existing or be rejected by backend guard. Multiple historical Subscription rows over time are allowed.

### 5.4 Subscription state transitions (source of truth: Stripe webhooks)
- Events consumed (v1 minimal): `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`. Invoice events are ignored in v1.
- Creation: Checkout success → `customer.subscription.created` (status `incomplete` or `active`), set Subscription row, set tier if `active`.
- Status update: `customer.subscription.updated` drives status/tier per mapping (non-active → downgrade to free; active → set paid tier per price_id).
- User cancel: `customer.subscription.updated` with cancel_at_period_end=true → record flag; entitlements become free once status is non-active (v1 assumes immediate downgrade on non-active).
- Immediate cancel: `customer.subscription.deleted` → downgrade to free.

### 5.5 Media-count enforcement lifecycle
- Enforcement point: any operation that would add a media to user’s default library. Callers must invoke `enforce_media_limit` before:
  - Ingestion/upload of new media (auto-add to default for the uploader).
  - Adding existing media to any library (explicit user add; auto-syncs to that user’s default).
- Joining a shared library does NOT auto-add its media to default; no quota check required purely for membership changes.
- If user over limit due to downgrade: existing media retained; all future adds fail until count <= limit (free limit=5).
- Deletions are always allowed; removing media can bring user under limit.

### 5.6 LLM usage enforcement lifecycle
- Calling subsystem (conversations/LLM) must invoke `check_and_maybe_increment_llm_usage` before making an LLM call; conversations spec must not mutate UsageRecord directly.
- If allowed: proceed with LLM call; UsageRecord incremented once per user message.
- If rejected: return quota error; caller still persists user message but skips LLM call.

## 6. invariants
- At most one active-ish `Subscription` per user (statuses in {active, past_due, unpaid, incomplete}); historical rows allowed beyond that.
- Free tier users have zero active-ish subscriptions; any existing non-active Subscription forces tier = free.
- Price→tier mapping must resolve; unknown price_id must not set a paid tier and must surface for manual review.
- At most one `UsageRecord` per (user_id, date).
- `User.subscription_tier` ∈ {free, personal, pro} and, if not free, must match the active Subscription’s price tier; if status is non-active, tier must be free.
- Free tier users must not be allowed to add media that would make default library count exceed 5; overage from downgrade is tolerated but cannot increase.
- Successful LLM call ⇒ exactly one increment of UsageRecord.message_count for that user/date.
- Over-quota LLM check must not increment UsageRecord.
- Default library holds media the user explicitly adds or uploads; media-count enforcement is evaluated on that distinct media count (shared-library membership alone does not add media).
- Stripe webhook processing is idempotent per event_id.

## 7. error handling
- Error codes and HTTP mapping (retriability = client should retry after action/time?):
  - `BILLING_NO_CUSTOMER` → 403 Forbidden; retriable after creating Stripe customer via checkout.
  - `BILLING_SUBSCRIPTION_REQUIRED` → 403 Forbidden (or 402 if we choose Payment Required) when subscription is delinquent/not-active and action requires paid tier; retriable after user resolves billing.
  - `BILLING_TIER_CONFLICT` → 409 Conflict; not retriable without state fix (e.g., multiple active subs).
  - `LIMIT_MEDIA_DEFAULT_EXCEEDED` → 403 Forbidden; retriable after deleting media or upgrading tier.
  - `LLM_QUOTA_EXCEEDED` → 429 Too Many Requests; retriable after UTC day rollover or tier upgrade.
  - `STRIPE_WEBHOOK_INVALID` → 400 Bad Request; not retriable (signature/body invalid).
  - `STRIPE_WEBHOOK_REPLAY` → 409 Conflict; not retriable (already processed).
  - `STRIPE_SESSION_CREATION_FAILED` → 502 Bad Gateway; retriable (transient Stripe failure).

## 8. performance / limits
- UsageRecord updates must be atomic under concurrency: single upsert with `ON CONFLICT (user_id, date) DO UPDATE SET message_count = message_count + :cost` guarded by date=UTC today; optionally wrapped in transaction/row-level lock to prevent double-increment on race.
- Media-count enforcement must use a consistent count query on default library distinct media_ids; rely on DB uniqueness of (library_id, media_id).
- LLM soft limit for pro: future; v1 only enforces daily message caps per table.
- Checkout/portal session caching is an implementation optimization, not part of the spec contract.

## 9. observability
- Metrics:
  - `billing.subscription.transition` (labels: from_status, to_status, tier).
  - `quota.llm.over_limit` counter.
  - `quota.llm.usage` counter (messages incremented).
  - `quota.media.over_limit` counter.
  - `stripe.webhook.failures` counter (by error code).
- Logs:
  - Subscription status changes with user_id, stripe_subscription_id, prior/current status, tier change.
  - Quota rejections (media/LLM) with user_id, tier, counts/limits.
  - Webhook validation failures with event_id and reason (no secrets).
- Alerts:
  - Stripe webhook failures sustained >N/min.
  - Unexpected tier conflict detection.

## 10. tests
- Unit:
  - Tier limit mapping function per table above.
  - `check_and_maybe_increment_llm_usage` concurrency: two concurrent increments result in correct total, no double beyond limit.
  - Media limit enforcement when count==limit and count>limit (post-downgrade).
  - Stripe event → status/tier mapping, immediate downgrade on non-active, and unknown price_id rejection.
- Integration:
  - LLM over-quota flow: user message stored, no LLM call, correct error.
  - Media add to default when at limit: rejected; after delete or upgrade: allowed.
  - Downgrade flow: active→non-active immediately downgrades tier; post-downgrade add is blocked.
  - Webhook idempotency: replayed event does not duplicate updates.
  - Checkout/portal endpoints produce usable URLs and set/create Subscription correctly after webhook.
  - Overview endpoint returns normalized `billing_state` and not raw Stripe status.

## 11. open questions
- Exact soft rate-limit policy for pro (thresholds, backoff) — outside v1; default to shared circuit breaker.
- Should we block library creation if it implies future media adds while over limit? (proposal: allow creation; enforce on actual add).

## 12. future extensions
- Token-based or cost-based LLM metering.
- Prepaid credits and usage-based billing.
- Seats/org plans and per-library billing.
- Coupons, trials, refunds, and prorations.
- Advanced abuse controls (per-IP/IP-country, device fingerprint) for LLM abuse.

