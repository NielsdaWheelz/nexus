# Nexus Auth & Accounts Specification (spec-auth-accounts.md)

## 1. Scope

**Purpose**  
Define authentication, sessioning, user lifecycle, profile updates, and the bootstrap process that creates the default library and initializes subscription tier. Provide contracts other subsystems use to identify the current user and read their subscription tier. Do not compose billing responses; frontend will call billing overview directly.

**Non-Goals**  
- No subscription/usage enforcement (owned by billing spec).  
- No visibility/permissions for libraries or social objects (owned by libraries/permissions and respective subsystems).  
- No Stripe calls or subscription mutations beyond reading billing-provided status.  
- No UI layout.  
- No schema redefinitions; defer to `domain-model.md`.

## 2. Dependencies
- Domain entities: `User`, `Library`, `LibraryUser` (bootstrap). `User.subscription_tier` is the only tier field auth reads or exposes.  
- Other specs: billing/subscriptions/usage, libraries/permissions/visibility, ingestion (for bootstrap add-to-default behavior), conversations/LLM (needs current user + tier), chunking/search (needs current user).  
- External services: optional email provider (only if email verification is later enabled; v1 assumes none).

## 3. Responsibilities
✅ Must do  
- Authenticate users (email+password).  
- Manage session creation/validation/expiration/logout.  
- Create user + default library + `LibraryUser`(role=`admin`) transactionally with `subscription_tier='free'`.  
- Expose current user (`/auth/me`) and profile update endpoint.  
- Expose `/auth/me`; billing overview stays at billing endpoint (no composite account overview).  
- Provide internal helper `get_current_user()` (or equivalent dependency) for other subsystems.

❌ Must not do  
- No direct Stripe or subscription state changes (billing-only).  
- No `subscription_tier` mutations except initial set-to-free on signup.  
- No media or LLM usage limits (billing-only).  
- No visibility enforcement for libraries/social objects.  
- No default-library runtime invariants; rely on libraries spec for share/rename/delete prevention.

## 4. External Interfaces

### 4.1 HTTP Endpoints

#### POST `/api/v1/auth/signup`
- Auth: public.  
- Request body: `{ email: string (lowercased), password: string, display_name: string (optional) }`.  
- Behavior: create user, set `subscription_tier='free'`, create default library (`is_default=true`, `owner_user_id=user.id`), create `LibraryUser` row (owner, role=`admin`), establish session cookie. All within a transaction; rollback on any failure.  
- Response 201: `{ user: { id, email, display_name, subscription_tier, created_at } }` and sets `HttpOnly Secure SameSite=Lax` cookie `nexus_session=<session_id>` with expiry per session policy.  
- Errors:  
  - 400 `AUTH_INVALID_EMAIL` (malformed)  
  - 400 `AUTH_WEAK_PASSWORD` (fails policy)  
  - 409 `AUTH_EMAIL_IN_USE`  
  - 500 `AUTH_SIGNUP_FAILED` (generic)

#### POST `/api/v1/auth/login`
- Auth: public.  
- Request body: `{ email: string, password: string }`.  
- Behavior: verify credentials, create session, set cookie.  
- Response 200: `{ user: { id, email, display_name, subscription_tier } }`.  
- Errors:  
  - 401 `AUTH_INVALID_CREDENTIALS`  
  - 423 `AUTH_ACCOUNT_DISABLED` (if we later support disable)  
  - 500 `AUTH_LOGIN_FAILED`

#### POST `/api/v1/auth/logout`
- Auth: requires valid session.  
- Behavior: invalidate session server-side; clear cookie (set expired).  
- Response 204 empty.  
- Errors:  
  - 401 `AUTH_NOT_AUTHENTICATED`

#### GET `/api/v1/auth/me`
- Auth: requires valid session.  
- Response 200: `{ user: { id, email, display_name, subscription_tier, created_at } }`.  
- Errors:  
  - 401 `AUTH_NOT_AUTHENTICATED` (missing/invalid/expired); use error_code to distinguish `AUTH_SESSION_EXPIRED` vs `AUTH_NOT_AUTHENTICATED`.

#### PATCH `/api/v1/account/profile`
- Auth: requires valid session.  
- Request body: `{ display_name?: string }` (only mutable field in v1; email/password changes are future).  
- Behavior: update allowed fields; never touches `subscription_tier`.  
- Response 200: `{ user: { id, email, display_name, subscription_tier } }`.  
- Errors:  
  - 400 `AUTH_INVALID_PROFILE` (validation)  
  - 401 `AUTH_NOT_AUTHENTICATED`

#### (Not provided) `/api/v1/account/overview`
- Not owned by auth/accounts. Frontend should call `/api/v1/auth/me` and billing’s `/api/v1/account/billing/overview` separately.

### 4.2 Internal Helpers
- `get_current_user(request) -> User`: validates session, returns user object with `id`, `subscription_tier`, and `is_authenticated` guarantee. Throws `AUTH_NOT_AUTHENTICATED`/`AUTH_SESSION_EXPIRED` on failure.  
- `require_authenticated(request)`: dependency wrapper for FastAPI routes.  
- `current_user_id(request) -> uuid`: for lightweight contexts.  
- Downstream contract: other subsystems read `user.subscription_tier`; they must not mutate it (billing-owned).

## 5. State & Lifecycles

### User Lifecycle
- States: `created` → `active`. No email verification in v1 (open question below). Optional future states: `disabled`, `deleted` (not implemented).  
- Creation atomically creates: User, Default Library, LibraryUser(admin). Failure at any step rolls back all.  
- Deletion/disable not supported in v1; login will continue to succeed unless disabled is added later.

### Session Lifecycle
- On login/signup: create `session_id` (random, 256-bit), store server-side record `{ session_id, user_id, created_at, expires_at, last_seen_ip, user_agent }` in Postgres table `sessions` (indexed on `session_id`, with scheduled cleanup by `expires_at`).  
- Cookie: `nexus_session` HttpOnly, Secure, SameSite=Lax, domain=frontend base, path=/, expiration matches `expires_at`.  
- Expiry: fixed 7-day lifetime from creation (no sliding refresh).  
- Validation: each request loads session from DB; if missing/invalid → 401 `AUTH_NOT_AUTHENTICATED`; if found but `expires_at` < now → 401 `AUTH_SESSION_EXPIRED` and delete row.  
- Logout: delete session row and clear cookie.  
- Rotation: only implicit on login/signup (new session replaces old); no periodic rotation in v1.

### Default Library Bootstrap
- Trigger: after User insert succeeds and before session issuance.  
- Inserts:  
  - Library row with `is_default=true`, `owner_user_id=user.id`, `name` default "Default" (not user-provided), non-shareable per libraries spec.  
  - LibraryUser row `{ library_id: default.id, user_id: user.id, role: 'admin' }`.  
- Transactional: all-or-nothing; failures bubble as 500 `AUTH_SIGNUP_FAILED`.  
- Postcondition: libraries subsystem invariants hold (single default library, single LibraryUser row, non-shareable). Auth spec delegates enforcement beyond creation to libraries subsystem.

## 6. Invariants (Local to Auth/Accounts)
- Each user is created with exactly one default library (is_default=true) and exactly one LibraryUser row (role=admin) for that library. Auth enforces creation only; ongoing invariants (no share/rename/delete, single membership) are enforced by libraries subsystem.  
- `subscription_tier` initialized to `free` on signup; only billing flows may change it.  
- Session cookie must map to a live server-side session; stateless JWT access without server-side presence is not allowed in v1.  
- Email uniqueness enforced case-insensitively.

## 7. Error Handling
- Error codes (prefix `AUTH_`):  
  - `AUTH_INVALID_EMAIL` → 400  
  - `AUTH_WEAK_PASSWORD` → 400  
  - `AUTH_EMAIL_IN_USE` → 409  
  - `AUTH_INVALID_CREDENTIALS` → 401  
  - `AUTH_NOT_AUTHENTICATED` → 401  
  - `AUTH_SESSION_EXPIRED` (expired cookie/session) → 401  
  - `AUTH_ACCOUNT_DISABLED` → 423 (reserved)  
  - `AUTH_SIGNUP_FAILED` / `AUTH_LOGIN_FAILED` → 500  
- Responses include machine code + human message; never leak whether email exists except in `AUTH_EMAIL_IN_USE` during signup.

## 8. Performance, Limits, and Security
- Session expiration: fixed 7-day lifetime.  
- Rate limits: not enforced in v1; may add simple IP/email limits later.  
- Password policy: min length 12, must include at least 1 letter and 1 number.  
- Password storage: Argon2id (memory-hard) with per-password salt; params tuned for 2025 hardware; store hash only.  
- Transport: HTTPS required; reject `Secure` cookie on HTTP.  
- CSRF: rely on SameSite=Lax and cookie-only auth; no CSRF token in v1. Pure API clients should not use cookies—use header tokens when added in future.  
- Brute-force protection: not enforced in v1; optional future lockout after repeated failures.  
- Session fixation: rotate session_id on login/signup only in v1.  
- PII minimization: logs must not store passwords; emails only in structured fields, not in raw error strings.

## 9. Observability
- SHOULD metrics (start small):  
  - `auth.signup.success`, `auth.signup.failure` (tag reason)  
  - `auth.login.success`, `auth.login.failure` (tag reason)  
  - `auth.logout.success`  
  - `auth.rate_limited` (tag endpoint, if added later)  
- SHOULD logs (structured):  
  - Signup events (user_id, email hash, outcome)  
  - Login attempts (user_id if known, email hash, ip, ua, outcome, rate-limit status)  
  - Session creation/invalidations  
  - Profile updates (fields changed, user_id)  
- NICE TO HAVE traces around signup/login/profile flows; include DB spans; tag with user_id when authenticated.

## 10. Test Matrix
- Unit  
  - Email normalization/uniqueness validation.  
  - Password policy + hashing/verification.  
  - Default library bootstrap transaction rollbacks on failure.  
  - Session creation/validation logic (DB-backed).  
  - Error mapping for invalid credentials vs expired session.  
- Integration  
  - Signup → auto default library + LibraryUser created, subscription_tier=free.  
  - Login → cookie set; `/auth/me` returns user.  
  - Logout → cookie cleared; subsequent `/auth/me` 401 (`AUTH_SESSION_EXPIRED` vs `AUTH_NOT_AUTHENTICATED`).  
  - Profile PATCH updates allowed fields only.  
  - Concurrent signup with same email → one succeeds, one 409.  
- Edge cases  
  - Expired session cookie → 401 with `AUTH_SESSION_EXPIRED`.  
  - Invalid session id (tampered) → 401 without server error.  
  - Bootstrap partial failure rolls back (no orphan Library row).  
  - Unicode email/display_name normalization (NFC) to avoid duplicates.

## 11. Open Questions
- Email verification: not in v1; accounts considered verified on signup.  
- Password reset: not in v1; manual admin reset acceptable for closed beta.  
- Account deletion / right-to-be-forgotten: not in v1; manual request to founder/admin.  
- Disabled accounts: who sets and how surfaced (423)?  
- Do we add CSRF tokens later if we expose cross-site POST entry points?  
- If/when to add session rotation beyond login and absolute caps.  
- Whether to add password breach checks (HIBP) later.

## 12. Future Extensions
- SSO (Google/Apple) with identity provider; sessions still cookie-based.  
- Email verification and password reset flows.  
- Account deletion/soft-delete with data retention and billing cancellation.  
- 2FA / WebAuthn.  
- Refresh-token split (short access token + long refresh) if we later expose pure API clients.  
- Device/session management UI (list + revoke).  
- Admin tooling for disabling accounts or forcing logout.

