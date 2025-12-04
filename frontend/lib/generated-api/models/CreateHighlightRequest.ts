/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for POST /highlights.
 *
 * Generic highlight creation endpoint supporting multiple media types and anchor types.
 * For v1, media_type="document" with anchor_type="text" (HTML/EPUB) or "pdf" (PDF) is supported.
 *
 * Anchor Types:
 * - "text": Character offsets into canonical_text (for HTML/EPUB documents)
 * - "pdf": PDF.js text layer offsets + page number (for PDF documents)
 *
 * Text Anchor Offset Semantics:
 * text_start and text_end are zero-indexed positions into canonical_text
 * treated as a sequence of Unicode code points.
 *
 * PDF Anchor Offset Semantics:
 * text_start and text_end are GLOBAL character offsets in the pdf.js text stream.
 * pdf_page_number and pdf_char_offset provide per-page coordinates.
 *
 * Attributes:
 * media_type: Type of media to highlight ("document" only for v1)
 * media_id: Typed media ID (e.g., doc_<uuid> for documents)
 * anchor_type: Type of anchor ("text" for html/epub, "pdf" for pdf)
 * text_start: Character offset start (>= 0)
 * text_end: Character offset end (> text_start)
 * pdf_page_number: PDF page number (1-based, required for anchor_type="pdf")
 * pdf_char_offset: Character offset within page (required for anchor_type="pdf")
 * quote: Selected text (required for anchor_type="pdf", computed for "text")
 * prefix: Context before quote (optional for anchor_type="pdf")
 * suffix: Context after quote (optional for anchor_type="pdf")
 */
export type CreateHighlightRequest = {
    /**
     * Type of media to highlight (only 'document' supported in v1)
     */
    media_type: string;
    /**
     * Typed media ID (e.g., doc_<uuid> for documents)
     */
    media_id: string;
    /**
     * Type of anchor ('text' for html/epub, 'pdf' for pdf)
     */
    anchor_type: 'text' | 'pdf';
    /**
     * Character offset start (>= 0)
     */
    text_start: number;
    /**
     * Character offset end (> text_start)
     */
    text_end: number;
    /**
     * PDF page number (1-based, required for anchor_type='pdf')
     */
    pdf_page_number?: number | null;
    /**
     * Character offset within page (required for anchor_type='pdf')
     */
    pdf_char_offset?: number | null;
    /**
     * Selected text (required for anchor_type='pdf', computed server-side for 'text')
     */
    quote?: string | null;
    /**
     * Context before quote (optional for anchor_type='pdf')
     */
    prefix?: string | null;
    /**
     * Context after quote (optional for anchor_type='pdf')
     */
    suffix?: string | null;
};

