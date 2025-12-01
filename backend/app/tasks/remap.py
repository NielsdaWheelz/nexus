"""Remap task stub for highlight remapping after canonicalization changes.

This is a stub implementation for Stage 7. The actual remap logic will be
implemented in a future PR.

When canonicalization produces a different canonical_hash, this task is enqueued
to remap existing highlights to the new canonical text.

Spec reference:
- spec/ingestion.md (remap triggers)
- spec/anchors.md (remapping algorithm for future implementation)
"""

from app.celery_app import celery_app


@celery_app.task(queue="documents")
def remap_highlights_for_document(document_id: str, old_hash: str, new_hash: str) -> dict:
    """Remap highlights when canonical text hash changes.

    STUB: This task is enqueued but does nothing in Phase 1.
    Implementation deferred to Stage 7.

    Args:
        document_id: Document UUID (as string)
        old_hash: Previous canonical_hash
        new_hash: New canonical_hash

    Returns:
        Dict with status (always "skipped" for now)

    Spec: When canonical_hash changes, remapping is triggered to update
    highlight anchors via fuzzy matching and edit distance algorithms.
    """
    # TODO Stage 7: Implement fuzzy matching, edit distance, remap logic
    return {
        "status": "skipped",
        "reason": "stub_not_implemented",
        "document_id": document_id,
        "old_hash": old_hash,
        "new_hash": new_hash,
    }
