1. principles for PRs in this project

these are constraints you should enforce on yourself + claude:
	1.	one axis of change per PR
	•	either:
	•	“new capability” (e.g. highlights backend), or
	•	“cross-cutting refactor” (rare), or
	•	“infra/tooling”.
	•	never “new schema + new jobs + new frontend + half a refactor”.
	2.	tight size envelope for claude
	•	sweet spot:
	•	backend PRs: ~3–8 core files changed, < 500–800 LOC.
	•	frontend PRs: same order of magnitude.
	•	if you feel the need to paste 10 files into claude, the PR is too big.
	3.	every PR grounded in spec
	•	for each PR, you should be able to say:
	•	“i am implementing §X.Y of spec/…”
	•	if you can’t point to the section, you’re probably inventing behavior on the fly.
	4.	tests + contracts first for important stuff
	•	for any PR that touches:
	•	anchoring, visibility, retrieval, or error envelopes,
	•	you want tests + explicit contracts in the same PR.
	•	don’t postpone invariants tests “for later”.
	5.	never mix schema + big logic changes
	•	alembic migrations: their own PR or tightly scoped with minimal logic.
	•	you do not want to debug application code + schema drift simultaneously.
	6.	consistent API shape
	•	all endpoints:
	•	use the canonical error envelope.
	•	follow { items, next_cursor, has_more } for list responses.
	•	use typed IDs.
	•	don’t let one endpoint go off-spec “just this once”.
	7.	visible “done” for each PR
	•	each PR should have a concrete observable outcome:
	•	“user can upload a PDF and see a ‘processing’ row”.
	•	“GET /documents returns typed IDs and error envelopes”.
	•	“highlight selection shows up and survives reload”.

⸻

2. phase 1 milestones (big picture)

phase 1 goals (per your constraint):
	•	docs: upload / extraction / canonical text / storage.
	•	reading UI: web articles + epub + pdf renderers.
	•	highlights + annotations (full pipeline).
	•	conversations + messages + per-message model field.
	•	basic LLM integration (no retrieval yet or minimal).
	•	link objects.
	•	libraries/visibility exist in schema, but we can defer full UI usage if needed.
	•	embeddings + retrieval: at least enough for “search in this doc” and “ask anything” across docs.

i’d group them in 6 milestones:
	1.	M0 – repo, tooling, logging, error envelopes, basic health.
	2.	M1 – auth + users + baseline schema/migrations.
	3.	M2 – documents + ingestion + canonical text (no highlights yet).
	4.	M3 – highlights + annotations + reader UI.
	5.	M4 – conversations/messages + chat frontend + minimal LLM.
	6.	M5 – embeddings/retrieval + links + hardening.

each milestone is several PRs.

⸻

3. how you use this with claude

for each PR:
	•	start with:
	•	“i am implementing PR 14: highlight selection + optimistic UI, which corresponds to spec sections X, Y, Z.”
	•	give claude:
	•	relevant spec snippets.
	•	only the files that belong to that concern.
	•	explicitly say:
	•	“do not touch X/Y/Z; this PR is only about […]”
	•	after implementing, run tests + a manual spec check:
	•	“does this behavior match the spec’s invariants?”