"""Canonical text extraction and canonicalization pipeline.

This module implements deterministic extraction of canonical text from documents:
- PDF: Extract text via PyMuPDF (fitz)
- EPUB: Unzip and extract text from content files
- HTML: Parse and extract visible text

All extraction is deterministic (same input → same output) and immutable.

Spec reference:
- spec/ingestion.md (canonicalization specification)
- spec/media.md (extraction rules per media type)
"""

import hashlib
import io
import json
import logging
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from lxml import html as lxml_html
except ImportError:
    lxml_html = None

from app.services.storage import StorageService
from app.tasks.remap import remap_highlights_for_document

# HTML extraction limits
MAX_HTML_INPUT_SIZE = 50 * 1024 * 1024  # 50 MB max for HTML input
READABILITY_HELPER_TIMEOUT = 30  # seconds


@dataclass
class CanonicalizationResult:
    """Result of document canonicalization.

    Fields:
    - canonical_text: Deterministic UTF-8 text extracted from source
    - canonical_hash: SHA256 of canonical_text
    - content_hash: SHA256 of original blob (for change detection)
    - structure: JSON structure (pages for PDF, sections for EPUB/HTML)
    - language: Language code (always "en" for Phase 1)
    - extractor_version: Version string of extraction tool (pdf-v1, epub-v1, html-v1)
    - text_byte_length: Length of canonical_text in bytes
    """

    canonical_text: str
    canonical_hash: str
    content_hash: str
    structure: dict
    language: str
    extractor_version: str
    text_byte_length: int


def _compute_sha256(data: bytes) -> str:
    """Compute SHA256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def extract_pdf(blob_bytes: bytes) -> tuple[str, dict, str]:
    """Extract canonical text from PDF using PyMuPDF.

    Args:
        blob_bytes: Raw PDF bytes

    Returns:
        Tuple of (canonical_text, structure, extractor_version)

    Raises:
        RuntimeError: If PyMuPDF not installed or PDF invalid
        ValueError: If extraction fails

    Spec: Extract text via page.get_text("text"), join with "\n\n"
    Structure tracks page boundaries as byte offsets in canonical text.
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) not installed. Install with: pip install pymupdf")

    try:
        doc = fitz.open(stream=blob_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}") from e

    pages = []
    text_parts = []
    current_byte_pos = 0

    for page_num in range(doc.page_count):
        try:
            page = doc[page_num]
            page_text = page.get_text("text")
        except Exception as e:
            raise ValueError(f"Failed to extract text from page {page_num}: {e}") from e

        # Track byte offsets
        text_start = current_byte_pos
        text_parts.append(page_text)
        current_byte_pos += len(page_text.encode("utf-8"))

        # Add newline separator (unless last page)
        if page_num < doc.page_count - 1:
            separator = "\n\n"
            text_parts.append(separator)
            current_byte_pos += len(separator.encode("utf-8"))

        text_end = current_byte_pos

        pages.append(
            {
                "page": page_num + 1,
                "text_start": text_start,
                "text_end": text_end,
            }
        )

    doc.close()

    canonical_text = "".join(text_parts)
    structure = {
        "type": "pdf",
        "pages": pages,
    }

    return canonical_text, structure, "pdf-v1"


def _extract_epub_spine_sections(epub_zip, opf_path: str, manifest: dict) -> tuple[list, list]:
    """Extract text sections from EPUB spine items.

    Returns: (sections, text_parts)
    """
    if lxml_html is None:
        raise RuntimeError("lxml not installed. Install with: pip install lxml")

    sections = []
    text_parts = []
    current_byte_pos = 0

    for spine_id, href in manifest.items():
        try:
            # Resolve href relative to OPF directory
            opf_dir = Path(opf_path).parent
            file_path = (opf_dir / href).as_posix()
            content = epub_zip.read(file_path).decode("utf-8")
        except (KeyError, UnicodeDecodeError):
            # Skip files that can't be read
            continue

        # Parse HTML and extract visible text
        tree = lxml_html.fromstring(content.encode("utf-8"))

        # Remove script and style tags
        for elem in tree.findall(".//script"):
            elem.drop_tree()
        for elem in tree.findall(".//style"):
            elem.drop_tree()

        # Find first heading for section title
        section_title = ""
        section_level = 1
        for heading in tree.findall(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6"):
            heading_text = (heading.text_content() or "").strip()
            if heading_text:
                section_title = heading_text
                section_level = int(heading.tag[1])
                break

        # Get all text content
        section_text = tree.text_content().strip()

        if section_text:
            text_start = current_byte_pos
            text_bytes = section_text.encode("utf-8")
            text_parts.append(section_text)
            current_byte_pos += len(text_bytes)

            # Add separator
            separator = "\n\n"
            text_parts.append(separator)
            current_byte_pos += len(separator.encode("utf-8"))

            sections.append(
                {
                    "id": spine_id,
                    "title": section_title,
                    "level": section_level,
                    "text_start": text_start,
                    "text_end": current_byte_pos,
                    "href": href,
                }
            )

    return sections, text_parts


def extract_epub(blob_bytes: bytes) -> tuple[str, dict, str]:
    """Extract canonical text from EPUB.

    EPUB is ZIP-based. Extract OPF (manifest), follow spine, extract text from XHTML/HTML files.
    Strip script/style tags. Track sections with headings.

    Args:
        blob_bytes: Raw EPUB bytes

    Returns:
        Tuple of (canonical_text, structure, extractor_version)

    Raises:
        ValueError: If EPUB invalid or extraction fails

    Spec: Extract sections, track heading levels, maintain text offsets.
    """
    try:
        # Unzip EPUB
        epub_zip = zipfile.ZipFile(io.BytesIO(blob_bytes))
    except Exception as e:
        raise ValueError(f"Failed to open EPUB as ZIP: {e}") from e

    try:
        # Read container.xml to find OPF path
        try:
            container_xml = epub_zip.read("META-INF/container.xml").decode("utf-8")
        except KeyError as e:
            raise ValueError("EPUB missing META-INF/container.xml") from e

        # Parse container to find rootfile
        container_tree = lxml_html.fromstring(container_xml.encode("utf-8"))
        rootfile_elem = container_tree.find(".//{*}rootfile")
        if rootfile_elem is None:
            raise ValueError("EPUB container.xml missing rootfile element")

        opf_path = rootfile_elem.get("full-path", "content.opf")

        # Read OPF (manifest + spine)
        try:
            opf_content = epub_zip.read(opf_path).decode("utf-8")
        except KeyError as e:
            raise ValueError(f"EPUB OPF file not found: {opf_path}") from e

        # Parse OPF to extract spine order
        opf_tree = lxml_html.fromstring(opf_content.encode("utf-8"))

        # Get spine itemref IDs in order
        spine_itemrefs = []
        for itemref in opf_tree.findall(".//{*}spine/{*}itemref"):
            idref = itemref.get("idref")
            if idref:
                spine_itemrefs.append(idref)

        # Get manifest (map id -> href)
        manifest = {}
        for item in opf_tree.findall(".//{*}manifest/{*}item"):
            item_id = item.get("id")
            href = item.get("href")
            if item_id and href:
                manifest[item_id] = href

        # Extract text from spine items
        sections, text_parts = _extract_epub_spine_sections(epub_zip, opf_path, manifest)

        canonical_text = "".join(text_parts)
        structure = {
            "type": "epub",
            "sections": sections,
            "toc": sections,  # Simplified: same as sections
        }

        return canonical_text, structure, "epub-v1"

    finally:
        epub_zip.close()


def _extract_html_sections(tree) -> tuple[list, list, int]:
    """Extract sections and text parts from HTML tree.

    Returns: (sections, text_parts, final_byte_pos)
    """
    sections = []
    text_parts = []
    current_byte_pos = 0
    heading_counter = {}

    # Find all headings (lxml findall doesn't support | syntax, so combine separate queries)
    headings = []
    for level in range(1, 7):
        headings.extend(tree.findall(f".//h{level}"))

    for heading in headings:
        heading_text = (heading.text_content() or "").strip()
        if not heading_text:
            continue

        heading_level = int(heading.tag[1])

        # Generate unique ID
        heading_counter[heading_level] = heading_counter.get(heading_level, 0)
        heading_id = f"h{heading_level}-{heading_counter[heading_level]}"
        heading_counter[heading_level] += 1

        text_start = current_byte_pos
        heading_bytes = heading_text.encode("utf-8")
        text_parts.append(heading_text)
        current_byte_pos += len(heading_bytes)

        # Add separator
        separator = "\n\n"
        text_parts.append(separator)
        current_byte_pos += len(separator.encode("utf-8"))

        sections.append(
            {
                "id": heading_id,
                "title": heading_text,
                "level": heading_level,
                "text_start": text_start,
                "text_end": current_byte_pos,
            }
        )

    # If no headings, extract all text as one section
    if not sections:
        all_text = tree.text_content().strip()
        if all_text:
            text_parts.append(all_text)
            current_byte_pos = len(all_text.encode("utf-8"))
            sections.append(
                {
                    "id": "content-0",
                    "title": "Content",
                    "level": 1,
                    "text_start": 0,
                    "text_end": current_byte_pos,
                }
            )

    return sections, text_parts, current_byte_pos


def extract_html(blob_bytes: bytes) -> tuple[str, dict, str]:
    """Extract canonical text from HTML using Mozilla Readability.

    Uses the Node.js readability_helper to extract article content intelligently,
    which handles cleaning up navigation, ads, etc. and extracts the main content.

    Args:
        blob_bytes: Raw HTML bytes

    Returns:
        Tuple of (canonical_text, structure, extractor_version)

    Raises:
        ValueError: If HTML invalid, too large, or extraction fails

    Spec: Extract text using Mozilla Readability algorithm.
    """
    # Check input size limit
    if len(blob_bytes) > MAX_HTML_INPUT_SIZE:
        raise ValueError(
            f"HTML input too large: {len(blob_bytes)} bytes exceeds limit of {MAX_HTML_INPUT_SIZE}"
        )

    try:
        # Try UTF-8 first, fall back to ISO-8859-1
        try:
            content = blob_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = blob_bytes.decode("iso-8859-1", errors="replace")
    except Exception as e:
        raise ValueError(f"Failed to decode HTML: {e}") from e

    try:
        # Call Node.js readability helper script
        helper_script = Path(__file__).parent / "readability_helper.js"
        result = subprocess.run(
            ["node", str(helper_script)],
            input=content.encode("utf-8"),
            capture_output=True,
            timeout=READABILITY_HELPER_TIMEOUT,
            check=False,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise ValueError(f"Readability helper failed: {stderr}")

        # Parse the JSON output
        output = json.loads(result.stdout.decode("utf-8"))
        canonical_text = output.get("text", "").strip()

        # Create structure with the title if available
        title = output.get("title", "Content").strip() or "Content"
        text_end = len(canonical_text.encode("utf-8")) if canonical_text else 0

        structure = {
            "type": "html",
            "title": title,
            "sections": [
                {
                    "id": "content-0",
                    "title": title,
                    "level": 1,
                    "text_start": 0,
                    "text_end": text_end,
                }
            ],
        }

        return canonical_text, structure, "html-v1"

    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse readability helper output: {e}") from e
    except subprocess.TimeoutExpired:
        raise ValueError(
            f"Readability helper timed out after {READABILITY_HELPER_TIMEOUT}s"
        ) from None
    except ValueError:
        # Re-raise ValueError as-is (includes size check, json parse, helper failure)
        raise
    except Exception as e:
        raise ValueError(f"HTML extraction failed: {e}") from e


def canonicalize_document(blob_key: str, source_kind: str) -> CanonicalizationResult:
    """Canonicalize a document by extracting deterministic text.

    This is the main entry point for extracting canonical text from a document.

    Args:
        blob_key: Storage key returned by StorageService.store_raw_blob()
        source_kind: Type of source ("pdf", "epub", "html")

    Returns:
        CanonicalizationResult with canonical_text, hashes, structure, version

    Raises:
        ValueError: If source_kind not supported or extraction fails
        FileNotFoundError: If blob not found
        RuntimeError: If extraction tool not available

    Spec reference:
    - spec/ingestion.md §2.2 (canonicalize_document job)
    - spec/media.md §2.3 (extraction rules)
    """
    # Load blob from storage
    storage = StorageService()
    try:
        with storage.open_blob(blob_key) as f:
            blob_bytes = f.read()
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Blob not found: {blob_key}") from e

    # Compute content_hash (hash of raw blob)
    content_hash = _compute_sha256(blob_bytes)

    # Dispatch by source_kind
    if source_kind == "pdf":
        canonical_text, structure, extractor_version = extract_pdf(blob_bytes)
    elif source_kind == "epub":
        canonical_text, structure, extractor_version = extract_epub(blob_bytes)
    elif source_kind == "html":
        canonical_text, structure, extractor_version = extract_html(blob_bytes)
    else:
        raise ValueError(f"Unsupported source_kind: {source_kind}")

    # Compute canonical_hash (hash of extracted text)
    canonical_hash = _compute_sha256(canonical_text.encode("utf-8"))

    # Compute text_byte_length
    text_byte_length = len(canonical_text.encode("utf-8"))

    return CanonicalizationResult(
        canonical_text=canonical_text,
        canonical_hash=canonical_hash,
        content_hash=content_hash,
        structure=structure,
        language="en",
        extractor_version=extractor_version,
        text_byte_length=text_byte_length,
    )


def run_ingest_document(session, document_id) -> dict:
    """Core ingestion logic: canonicalize, hash, update document status.

    This is the pure business logic for document ingestion. It should be called
    by the ingest_document Celery task, but can also be called directly from
    tests or other services.

    Status machine:
    - pending      → processing
    - failed       → processing (retry)
    - ready+same   → no-op (content_hash unchanged)
    - ready+new    → processing (content changed)
    - processing   → should not be re-entered concurrently (assert)

    Args:
        session: SQLAlchemy Session
        document_id: Document UUID or string UUID

    Returns:
        Dict with status and result metadata

    Raises:
        ValueError: If document_id invalid or document not found
        Exception: On extraction/database failure
    """
    from datetime import datetime, timezone
    from uuid import UUID

    from sqlalchemy import select

    from app.core.errors import ErrorCode
    from app.models.document import Document

    logger = logging.getLogger(__name__)

    # Parse document_id if string
    if isinstance(document_id, str):
        try:
            doc_uuid = UUID(document_id)
        except ValueError as e:
            logger.error(f"Invalid document_id format: {document_id}")
            raise ValueError(f"Invalid document_id format: {document_id}") from e
    else:
        doc_uuid = document_id

    # Fetch document with lock for atomic update
    stmt = select(Document).where(Document.id == doc_uuid).with_for_update()
    doc = session.execute(stmt).scalar_one_or_none()

    if not doc:
        logger.error(f"Document not found: {document_id}")
        raise ValueError(f"Document not found: {document_id}")

    # Status machine: verify we can transition
    logger.info(f"Ingesting document {document_id}, current status: {doc.status}")

    if doc.status == "processing":
        # Should not re-enter processing concurrently
        logger.warning(f"Document {document_id} is already being processed (concurrent entry?)")
        return {"status": "skipped", "reason": "already_processing"}

    if doc.status == "ready":
        # Check if content changed (by comparing content_hash)
        # If we already extracted and content hasn't changed, skip
        if doc.canonical_text and doc.content_hash == doc.content_hash:
            logger.info(f"Document {document_id} already ready with same hash, skipping")
            return {"status": "skipped", "reason": "already_ready_same_hash"}

    # Transition to processing
    doc.status = "processing"
    doc.retries_count += 1
    doc.last_attempted_at = datetime.now(timezone.utc)
    doc.error_code = None
    doc.error_message = None

    session.flush()
    logger.info(f"Transitioned document {document_id} to processing")

    # Canonicalize document
    try:
        # Convert MIME type to source_kind
        mime_type = doc.original_mime_type
        if not mime_type:
            raise ValueError("MIME type is required")

        mime_type_lower = mime_type.lower()
        if "pdf" in mime_type_lower:
            source_kind = "pdf"
        elif "epub" in mime_type_lower:
            source_kind = "epub"
        elif "html" in mime_type_lower or "text/html" in mime_type_lower:
            source_kind = "html"
        else:
            raise ValueError(f"Unsupported MIME type: {mime_type}")

        result = canonicalize_document(
            blob_key=doc.original_blob_key,
            source_kind=source_kind,
        )
    except Exception as e:
        logger.error(f"Canonicalization failed for {document_id}: {e}")
        # Set failure status and re-raise for retry
        doc.status = "failed"
        doc.error_code = ErrorCode.EXTRACTION_FAILED.value
        doc.error_message = str(e)[:500]
        session.flush()
        raise

    # Store old canonical_hash to detect changes (for remap trigger)
    old_anchored_hash = doc.anchored_content_hash

    # Update document with extraction results
    doc.canonical_text = result.canonical_text
    doc.canonical_hash = result.canonical_hash
    doc.content_hash = result.content_hash
    doc.structure = result.structure
    doc.language = result.language
    doc.extractor_version = result.extractor_version
    doc.text_byte_length = result.text_byte_length

    # Set anchored_content_hash on first ingestion (if null)
    if doc.anchored_content_hash is None:
        doc.anchored_content_hash = result.canonical_hash

    # Transition to ready
    doc.status = "ready"
    session.flush()

    logger.info(f"Successfully ingested document {document_id}")

    # Trigger remap if canonical_hash changed (and we had anchors before)
    if old_anchored_hash is not None and old_anchored_hash != result.canonical_hash:
        logger.info(f"Canonical hash changed for {document_id}, enqueuing remap job")
        remap_highlights_for_document.delay(str(doc_uuid), old_anchored_hash, result.canonical_hash)

    return {
        "status": "success",
        "document_id": str(doc_uuid),
        "canonical_hash": result.canonical_hash,
        "content_hash": result.content_hash,
        "text_byte_length": result.text_byte_length,
    }
