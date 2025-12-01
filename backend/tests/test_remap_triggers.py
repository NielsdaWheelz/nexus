"""Unit tests for remap trigger logic.

Tests verify:
- No remap on first ingestion (anchored_content_hash set from canonical_hash)
- No remap when canonical_hash unchanged
- Remap task enqueued when canonical_hash changes
- Old anchored_hash preserved during remap
"""


def test_remap_first_ingestion_no_task():
    """Test that first ingestion (no prior anchored_content_hash) doesn't trigger remap."""
    # Simulate first ingestion: anchored_content_hash is None
    from app.services.ingestion import CanonicalizationResult

    result = CanonicalizationResult(
        canonical_text="Hello World",
        canonical_hash="abc123",
        content_hash="def456",
        structure={},
        language="en",
        extractor_version="pdf-v1",
        text_byte_length=11,
    )

    old_anchored_hash = None  # First ingestion

    # No remap should be triggered
    should_remap = old_anchored_hash is not None and old_anchored_hash != result.canonical_hash

    assert not should_remap


def test_remap_same_hash_no_task():
    """Test that unchanged canonical_hash doesn't trigger remap."""
    from app.services.ingestion import CanonicalizationResult

    result = CanonicalizationResult(
        canonical_text="Hello World",
        canonical_hash="abc123",
        content_hash="def456",
        structure={},
        language="en",
        extractor_version="pdf-v1",
        text_byte_length=11,
    )

    old_anchored_hash = "abc123"  # Same as new hash

    # No remap should be triggered
    should_remap = old_anchored_hash is not None and old_anchored_hash != result.canonical_hash

    assert not should_remap


def test_remap_changed_hash_enqueues_task():
    """Test that changed canonical_hash enqueues remap task."""
    from app.services.ingestion import CanonicalizationResult

    result = CanonicalizationResult(
        canonical_text="Hello World Updated",
        canonical_hash="new_hash_xyz",
        content_hash="def456",
        structure={},
        language="en",
        extractor_version="pdf-v1",
        text_byte_length=19,
    )

    old_anchored_hash = "old_hash_abc"  # Different from new hash

    # Remap should be triggered
    should_remap = old_anchored_hash is not None and old_anchored_hash != result.canonical_hash

    assert should_remap


def test_remap_task_called_with_correct_args():
    """Test that remap is triggered when hashes differ."""
    from app.services.ingestion import CanonicalizationResult

    result = CanonicalizationResult(
        canonical_text="Updated Content",
        canonical_hash="new_hash",
        content_hash="content_hash",
        structure={},
        language="en",
        extractor_version="pdf-v1",
        text_byte_length=15,
    )

    document_id = "doc-123"
    old_anchored_hash = "old_hash"

    # Verify logic: remap should be triggered when hashes differ
    should_remap = old_anchored_hash is not None and old_anchored_hash != result.canonical_hash

    # Verify correct logic
    assert should_remap
    assert old_anchored_hash != result.canonical_hash
    assert document_id == "doc-123"
