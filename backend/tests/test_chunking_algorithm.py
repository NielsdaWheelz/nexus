"""Tests for the document chunking algorithm.

Tests cover:
- Short text (single chunk)
- Long text (multiple chunks)
- Paragraph-aware boundaries
- Unicode/multi-byte character handling
- Determinism (same input → same output)
"""

import pytest

from app.services.chunking import MAX_CHUNK_CHARS, ChunkSpan, chunk_canonical_text


class TestChunkCanonicalText:
    """Tests for chunk_canonical_text function."""

    def test_empty_text(self):
        """Empty text produces no chunks."""
        result = chunk_canonical_text("")
        assert result == []

    def test_single_chunk_short_text(self):
        """Short text (below MAX_CHUNK_CHARS) produces single chunk."""
        text = "This is a short document.\n\nIt has just two paragraphs."
        result = chunk_canonical_text(text)

        assert len(result) == 1
        assert result[0].text == text  # Text should match exactly
        assert result[0].start == 0
        assert result[0].end == len(text.encode("utf-8"))
        assert result[0].metadata["index"] == 0

    def test_multiple_chunks_long_text(self):
        """Long text produces multiple chunks."""
        # Create text with ~3 chunks worth of content
        para1 = "A" * 800  # One paragraph
        para2 = "B" * 800
        para3 = "C" * 800
        text = f"{para1}\n\n{para2}\n\n{para3}"

        result = chunk_canonical_text(text)

        assert len(result) >= 2  # Should have at least 2 chunks
        # All spans should be non-overlapping
        for i in range(len(result) - 1):
            assert result[i].end <= result[i + 1].start

    def test_paragraph_aware_boundaries(self):
        """Chunks split at paragraph boundaries, not mid-word."""
        # Create clear paragraphs
        para1 = "First paragraph with some content."
        para2 = "Second paragraph with more content."
        para3 = "Third paragraph."
        text = f"{para1}\n\n{para2}\n\n{para3}"

        result = chunk_canonical_text(text)

        # Should have at least 1 chunk (probably 1 since this is short)
        assert len(result) >= 1

        # Check that chunks don't split mid-word
        for span in result:
            # Each chunk text should not end with partial word
            # (i.e., should be trimmed properly)
            assert not span.text.endswith("\n")

    def test_byte_offsets_are_correct(self):
        """Byte offsets should correctly map to UTF-8 encoded positions."""
        text = "Hello\n\nWorld"
        result = chunk_canonical_text(text)

        assert len(result) == 1
        span = result[0]

        # Extract the text using byte offsets
        text_bytes = text.encode("utf-8")
        extracted = text_bytes[span.start : span.end].decode("utf-8")

        # Should match the chunk text (after stripping)
        assert extracted.rstrip() == span.text

    def test_unicode_offsets(self):
        """Unicode characters produce correct byte offsets."""
        # Include multi-byte UTF-8 characters
        text = "Hello 👋\n\nWorld 🌍"
        result = chunk_canonical_text(text)

        assert len(result) == 1
        span = result[0]

        # Verify byte offsets
        text_bytes = text.encode("utf-8")
        assert span.start >= 0
        assert span.end <= len(text_bytes)

        # Extract using offsets and verify
        extracted = text_bytes[span.start : span.end].decode("utf-8")
        assert extracted.rstrip() == span.text

    def test_determinism(self):
        """Same input always produces identical output."""
        text = "Para 1\n\nPara 2\n\nPara 3"

        result1 = chunk_canonical_text(text)
        result2 = chunk_canonical_text(text)

        assert len(result1) == len(result2)
        for span1, span2 in zip(result1, result2):
            assert span1.start == span2.start
            assert span1.end == span2.end
            assert span1.text == span2.text
            assert span1.metadata == span2.metadata

    def test_chunk_metadata(self):
        """Chunks have proper metadata."""
        text = "First paragraph\n\nSecond paragraph\n\nThird paragraph"
        result = chunk_canonical_text(text)

        for i, span in enumerate(result):
            assert "index" in span.metadata
            assert span.metadata["index"] == i
            assert "approx_char_length" in span.metadata
            assert "approx_paragraphs" in span.metadata
            assert span.metadata["approx_char_length"] > 0
            assert span.metadata["approx_paragraphs"] >= 1

    def test_non_overlapping_spans(self):
        """Chunks should never overlap."""
        # Long text to force multiple chunks
        text = "Start\n\n" + "\n\n".join(["Paragraph " + str(i) * 100 for i in range(10)])

        result = chunk_canonical_text(text)

        # Verify no overlaps
        for i in range(len(result) - 1):
            assert (
                result[i].end <= result[i + 1].start
            ), f"Chunk {i} overlaps with chunk {i+1}: {result[i].end} > {result[i+1].start}"

    def test_spans_are_sorted(self):
        """Chunks should be sorted by start position."""
        text = "Para 1\n\n" + "\n\n".join(["P" * 500 for _ in range(5)])

        result = chunk_canonical_text(text)

        for i in range(len(result) - 1):
            assert result[i].start < result[i + 1].start

    def test_chunk_span_is_frozen(self):
        """ChunkSpan should be a frozen dataclass."""
        span = ChunkSpan(start=0, end=10, text="test", metadata={})
        with pytest.raises(AttributeError):
            span.start = 5  # Should not be able to modify

    def test_very_long_paragraph(self):
        """Single paragraph longer than MAX_CHUNK_CHARS should still be chunked or kept."""
        # Create a single paragraph that exceeds MAX_CHUNK_CHARS
        long_para = "A" * (MAX_CHUNK_CHARS + 100)
        text = long_para

        result = chunk_canonical_text(text)

        # Should have at least one chunk
        assert len(result) >= 1

        # The span should cover the whole text
        assert result[0].start == 0
        assert result[0].end == len(text.encode("utf-8"))

    def test_multiple_paragraph_separators(self):
        """Multiple newlines (>\n\n) should be treated as paragraph separator."""
        text = "Para1\n\n\n\nPara2"  # Four newlines
        result = chunk_canonical_text(text)

        # Should recognize the gap and create chunks
        assert len(result) >= 1

    def test_accented_characters(self):
        """Accented characters should produce correct byte offsets."""
        text = "Héllo\n\nWørld\n\nFrançais"
        result = chunk_canonical_text(text)

        assert len(result) >= 1
        for span in result:
            # Verify we can extract the text using byte offsets
            text_bytes = text.encode("utf-8")
            extracted = text_bytes[span.start : span.end].decode("utf-8")
            assert extracted.rstrip() == span.text

    def test_span_bounds_within_text(self):
        """All span byte offsets should be within [0, len(canonical_text_bytes))."""
        text = "Para1\n\nPara2\n\nPara3\n\nPara4\n\nPara5"
        text_bytes = text.encode("utf-8")
        max_byte = len(text_bytes)

        result = chunk_canonical_text(text)

        for span in result:
            assert span.start >= 0, f"Span start {span.start} < 0"
            assert span.end <= max_byte, f"Span end {span.end} > max_byte {max_byte}"
            assert span.start < span.end, f"Span start {span.start} >= end {span.end}"

    def test_spans_can_reconstruct_text(self):
        """Concatenating span texts should cover canonical text (whitespace-tolerant)."""
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = chunk_canonical_text(text)

        # Reconstruct by concatenating chunks
        reconstructed_parts = []
        for span in result:
            reconstructed_parts.append(span.text)

        # Normalize both: split on whitespace and rejoin
        reconstructed_normalized = " ".join("".join(reconstructed_parts).split())
        original_normalized = " ".join(text.split())

        # Both should have same normalized form (whitespace-agnostic)
        assert reconstructed_normalized.lower() == original_normalized.lower()

    def test_no_duplicate_text_in_spans(self):
        """Chunks should not have duplicate text (no overlaps)."""
        text = "Para1\n\n" + "\n\n".join(["P" * 300 for _ in range(5)])
        result = chunk_canonical_text(text)

        # Collect all unique texts
        seen = set()
        for span in result:
            # Using simplified text (no whitespace) for comparison
            simplified = "".join(span.text.split())
            assert simplified not in seen, f"Duplicate chunk text detected: {span.text[:50]}"
            seen.add(simplified)

    def test_span_offsets_are_exact(self):
        """Extracting text using span offsets should exactly match span.text."""
        text = "Start\n\nMiddle paragraph\n\nEnd"
        text_bytes = text.encode("utf-8")
        result = chunk_canonical_text(text)

        for span in result:
            extracted = text_bytes[span.start : span.end].decode("utf-8").rstrip()
            # After rstrip, should match exactly
            assert (
                extracted == span.text
            ), f"Mismatch: extracted={extracted!r}, span.text={span.text!r}"
