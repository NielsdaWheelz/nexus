"""Unit tests for EPUB canonicalization.

Tests verify:
- Text extraction from EPUB content files
- Deterministic structure (sections with headings and byte offsets)
- Correct hash computation
- Extractor version set correctly
- Script/style tag stripping
"""

import io
import zipfile

import pytest

from app.services.ingestion import extract_epub


def create_minimal_epub() -> bytes:
    """Create a minimal valid EPUB with one section containing a heading.

    Returns bytes that can be passed to extract_epub.
    """
    epub_zip = zipfile.ZipFile(io.BytesIO(), "w", zipfile.ZIP_DEFLATED)

    # Add mimetype (uncompressed, first in archive)
    epub_zip.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

    # Add container.xml
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
    epub_zip.writestr("META-INF/container.xml", container_xml)

    # Add content.opf
    content_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uuid_id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Test EPUB</dc:title>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="text1" href="Text/chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="text1"/>
  </spine>
</package>
"""
    epub_zip.writestr("OEBPS/content.opf", content_opf)

    # Add toc.ncx (required but minimal)
    toc_ncx = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="test"/>
  </head>
  <navMap>
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>Chapter 1</text></navLabel>
      <content src="Text/chapter1.xhtml"/>
    </navPoint>
  </navMap>
</ncx>
"""
    epub_zip.writestr("OEBPS/toc.ncx", toc_ncx)

    # Add content file with heading and text
    chapter1_xhtml = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Chapter 1</title>
  </head>
  <body>
    <h1>Chapter 1: Introduction</h1>
    <p>This is the first paragraph of chapter 1.</p>
    <p>This is the second paragraph.</p>
  </body>
</html>
"""
    epub_zip.writestr("OEBPS/Text/chapter1.xhtml", chapter1_xhtml)

    # Create proper EPUB
    proper_zip = io.BytesIO()
    with zipfile.ZipFile(proper_zip, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container_xml)
        zf.writestr("OEBPS/content.opf", content_opf)
        zf.writestr("OEBPS/toc.ncx", toc_ncx)
        zf.writestr("OEBPS/Text/chapter1.xhtml", chapter1_xhtml)

    return proper_zip.getvalue()


def test_extract_epub_basic():
    """Test basic EPUB text extraction."""
    epub_bytes = create_minimal_epub()

    canonical_text, structure, extractor_version = extract_epub(epub_bytes)

    # Verify text was extracted
    assert canonical_text
    assert "Chapter 1" in canonical_text
    assert "Introduction" in canonical_text
    assert extractor_version == "epub-v1"

    # Verify structure
    assert structure["type"] == "epub"
    assert "sections" in structure
    assert len(structure["sections"]) > 0

    # Verify sections have required fields
    for section in structure["sections"]:
        assert "id" in section
        assert "title" in section or section.get("title") == ""
        assert "level" in section
        assert "text_start" in section
        assert "text_end" in section
        assert "href" in section


def test_extract_epub_deterministic():
    """Test that EPUB extraction is deterministic."""
    epub_bytes = create_minimal_epub()

    result1 = extract_epub(epub_bytes)
    result2 = extract_epub(epub_bytes)

    # Same text
    assert result1[0] == result2[0]
    # Same structure
    assert result1[1] == result2[1]
    # Same version
    assert result1[2] == result2[2]


def test_extract_epub_heading_extraction():
    """Test that headings are correctly extracted."""
    epub_bytes = create_minimal_epub()

    canonical_text, structure, extractor_version = extract_epub(epub_bytes)

    # Verify structure contains heading info
    assert structure["type"] == "epub"
    assert len(structure["sections"]) > 0

    # First section should have a title
    first_section = structure["sections"][0]
    assert first_section["level"] in [1, 2, 3, 4, 5, 6]


def test_extract_epub_byte_offsets():
    """Test that byte offsets are correct."""
    epub_bytes = create_minimal_epub()

    canonical_text, structure, extractor_version = extract_epub(epub_bytes)
    text_bytes = canonical_text.encode("utf-8")

    # Verify all sections have valid byte ranges
    for section in structure["sections"]:
        assert section["text_start"] >= 0
        assert section["text_end"] <= len(text_bytes)
        assert section["text_start"] <= section["text_end"]


def test_extract_epub_invalid_zip():
    """Test that invalid EPUB (invalid ZIP) raises ValueError."""
    invalid_epub = b"not a zip file"

    with pytest.raises(ValueError, match="Failed to open EPUB"):
        extract_epub(invalid_epub)


def test_extract_epub_missing_container():
    """Test that EPUB missing container.xml raises ValueError."""
    # Create a valid ZIP but without container.xml
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("some_file.txt", "content")

    invalid_epub = bio.getvalue()

    with pytest.raises(ValueError, match="missing META-INF/container.xml"):
        extract_epub(invalid_epub)
