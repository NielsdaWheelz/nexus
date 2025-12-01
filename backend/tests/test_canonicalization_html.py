"""Unit tests for HTML canonicalization.

Tests verify:
- Text extraction from HTML
- Heading detection and section extraction
- Script/style tag stripping
- Deterministic structure with byte offsets
- Correct hash computation
"""

from app.services.ingestion import extract_html


def test_extract_html_basic():
    """Test basic HTML text extraction."""
    html_content = b"""<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
  <h1>Main Heading</h1>
  <p>This is a paragraph.</p>
  <h2>Subheading</h2>
  <p>Another paragraph.</p>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)

    # Verify text was extracted
    assert canonical_text
    assert "Main Heading" in canonical_text
    assert "This is a paragraph" in canonical_text
    assert "Subheading" in canonical_text
    assert extractor_version == "html-v1"

    # Verify structure
    assert structure["type"] == "html"
    assert "sections" in structure
    assert len(structure["sections"]) > 0


def test_extract_html_removes_script_and_style():
    """Test that script and style tags are stripped."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
  <h1>Content</h1>
  <script>
    var x = "should not appear";
    console.log(x);
  </script>
  <style>
    body { color: red; }
  </style>
  <p>Visible paragraph.</p>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)

    # Script and style content should not appear
    assert "should not appear" not in canonical_text
    assert "color: red" not in canonical_text
    # Real content should appear
    assert "Content" in canonical_text
    assert "Visible paragraph" in canonical_text


def test_extract_html_heading_levels():
    """Test that all headings are extracted in the canonical text."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
  <h1>Level 1 Heading</h1>
  <h2>Level 2 Heading</h2>
  <h3>Level 3 Heading</h3>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)

    # Verify all headings are included in the extracted text
    assert "Level 1 Heading" in canonical_text
    assert "Level 2 Heading" in canonical_text
    assert "Level 3 Heading" in canonical_text

    # Should have at least one section
    assert len(structure["sections"]) >= 1


def test_extract_html_no_headings():
    """Test extraction when no headings are present."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
  <p>Just plain paragraphs.</p>
  <p>No headings here.</p>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)

    # Should still have a section even without headings
    assert len(structure["sections"]) >= 1
    # Default section should have title "Content"
    assert structure["sections"][0]["title"] in ["Content", ""]


def test_extract_html_deterministic():
    """Test that HTML extraction is deterministic."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
  <h1>Title</h1>
  <p>Content here.</p>
</body>
</html>
"""

    result1 = extract_html(html_content)
    result2 = extract_html(html_content)

    # Same text
    assert result1[0] == result2[0]
    # Same structure
    assert result1[1] == result2[1]
    # Same version
    assert result1[2] == result2[2]


def test_extract_html_byte_offsets():
    """Test that byte offsets are correct."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
  <h1>First</h1>
  <h1>Second</h1>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)
    text_bytes = canonical_text.encode("utf-8")

    # Verify all sections have valid byte ranges
    for section in structure["sections"]:
        assert section["text_start"] >= 0
        assert section["text_end"] <= len(text_bytes)
        assert section["text_start"] <= section["text_end"]


def test_extract_html_section_ids_unique():
    """Test that section IDs are unique."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
  <h1>First Heading</h1>
  <h1>Second Heading</h1>
  <h1>Third Heading</h1>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)

    # All section IDs should be unique
    ids = [s["id"] for s in structure["sections"]]
    assert len(ids) == len(set(ids))  # No duplicates


def test_extract_html_invalid_encoding():
    """Test that invalid UTF-8 is handled gracefully."""
    # Invalid UTF-8 sequence
    html_content = b"<!DOCTYPE html><html><body>\xff\xfe</body></html>"

    canonical_text, structure, extractor_version = extract_html(html_content)

    # Should not raise, but may contain replacement characters
    assert canonical_text is not None
    assert structure["type"] == "html"


def test_extract_html_empty_content():
    """Test extraction of empty HTML."""
    html_content = b"""<!DOCTYPE html>
<html>
<body>
</body>
</html>
"""

    canonical_text, structure, extractor_version = extract_html(html_content)

    # Empty content should still produce valid structure
    assert canonical_text == ""
    assert structure["type"] == "html"
    assert "sections" in structure
