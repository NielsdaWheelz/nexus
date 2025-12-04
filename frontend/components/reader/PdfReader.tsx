"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useDocumentBlob } from "@/lib/hooks/useDocumentBlob";
import { useDocumentHighlights } from "@/lib/hooks/useHighlights";
import { useUIStore } from "@/lib/state/ui";
import {
  applyPdfHighlightsToPage,
  clearPdfHighlightsFromPage,
  findHighlightElement,
} from "@/lib/anchoring/pdfAnchoring";
import type { PdfHighlightAnchor } from "@/lib/anchoring/pdfAnchoring";
import type { DocumentListItem } from "@/lib/generated-api";

// PDF.js types
// Note: TextItem is not directly exported from pdfjs-dist, so we define it locally
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";

/**
 * Text item from pdf.js getTextContent().
 * This matches the TextItem type from pdfjs-dist/types/src/display/api.d.ts
 * but is not directly exported from the main module.
 */
interface PdfTextItem {
  str: string;
  dir: string;
  transform: number[];
  width: number;
  height: number;
  fontName: string;
  hasEOL: boolean;
}

/**
 * Props for the PdfReader component.
 */
export interface PdfReaderProps {
  /** Document ID to render */
  documentId: string;
  /** Document metadata (for title display, source_kind verification) */
  document: DocumentListItem;
}

/**
 * Text layer item with positioning information.
 */
interface TextLayerItem {
  /** The text string content */
  str: string;
  /** X position in PDF units */
  x: number;
  /** Y position in PDF units (transformed for canvas coordinates) */
  y: number;
  /** Width of text in PDF units */
  width: number;
  /** Height of text in PDF units */
  height: number;
  /** Font size in PDF units */
  fontSize: number;
  /** Global character offset within the document's text stream */
  charOffset: number;
}

/**
 * Page state for tracking rendered pages.
 */
interface PageState {
  pageNumber: number;
  textItems: TextLayerItem[];
  width: number;
  height: number;
}

/**
 * Number of pages to render initially.
 */
const INITIAL_PAGE_COUNT = 3;

/**
 * Number of pages to add when scrolling.
 */
const PAGE_INCREMENT = 3;

/**
 * PdfReader - Read-only PDF renderer using pdf.js with highlight support.
 *
 * Features:
 * - Renders PDF pages with canvas for visuals
 * - Creates text layer overlay for anchoring highlights
 * - Progressive loading: loads first N pages, then more as user scrolls
 * - Text layer spans have data-page-number and data-char-offset attributes
 * - Renders highlights as overlays on the text layer
 * - Integrates with UI store for active highlight state
 *
 * TEXT LAYER ANCHOR SEMANTICS (data-char-offset):
 * See: spec/anchors.md § 1.3.1 Offset Semantics
 *
 * `data-char-offset` is the 0-based GLOBAL character offset of this span's
 * start within the concatenation of all text items across ALL pages.
 * This corresponds to `text_start` in the highlight anchor schema.
 *
 * Computation:
 * - Iterate pages 1..N in order
 * - For each page, iterate pdf.js textContent.items in order
 * - Each text item's charOffset = cumulative character count so far
 * - Increment by textItem.str.length
 *
 * Does NOT include:
 * - No separator whitespace/newlines between text items
 * - No page separators or boundary markers
 * - Raw concatenation of textItem.str values
 *
 * When creating highlights, anchoring code MUST compute:
 * - `text_start`, `text_end`: from data-char-offset (already global)
 * - `pdf_page_number`: from data-page-number of first selected span
 * - `pdf_char_offset`: text_start minus cumulative text length of prior pages
 * - `pdf_file_hash`: SHA256 of the PDF binary
 *
 * Lazy loading note: When renderedPageCount increases, ALL pages 1..N are
 * re-processed from scratch to ensure correct global offsets. This is correct
 * but potentially slow for large documents (optimization opportunity).
 *
 * PR9: Read-only highlight rendering. No highlight creation yet.
 */
export function PdfReader({ documentId, document }: PdfReaderProps) {
  const { data: pdfBuffer, isLoading, isError, error } = useDocumentBlob(documentId);
  
  // Fetch highlights for this document
  const { highlights } = useDocumentHighlights(documentId);
  
  // UI store for active highlight state
  const activeHighlightId = useUIStore((s) => s.activeHighlightId);
  const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);
  
  // PDF document reference
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  
  // Page rendering state
  const [renderedPageCount, setRenderedPageCount] = useState(INITIAL_PAGE_COUNT);
  const [pages, setPages] = useState<PageState[]>([]);
  
  // Global character offset tracker for text layer
  const globalCharOffset = useRef(0);
  
  // Container ref for scroll detection
  const containerRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Compute page offset ranges for filtering highlights
  // This maps page numbers to their global character offset ranges
  const pageOffsetRanges = useMemo(() => {
    const ranges: Array<{ pageNumber: number; minOffset: number; maxOffset: number }> = [];
    for (const page of pages) {
      if (page.textItems.length === 0) {
        ranges.push({ pageNumber: page.pageNumber, minOffset: 0, maxOffset: 0 });
      } else {
        const minOffset = page.textItems[0].charOffset;
        const lastItem = page.textItems[page.textItems.length - 1];
        const maxOffset = lastItem.charOffset + lastItem.str.length;
        ranges.push({ pageNumber: page.pageNumber, minOffset, maxOffset });
      }
    }
    return ranges;
  }, [pages]);

  // Filter PDF highlights and convert to PdfHighlightAnchor format per page
  // PDF highlights use pdf_page_number + pdf_char_offset (per-page coordinates)
  // We convert to global character offsets for the text layer DOM
  const highlightsByPage = useMemo(() => {
    const byPage = new Map<number, PdfHighlightAnchor[]>();
    
    // Only process PDF anchor highlights for the PDF reader
    const pdfHighlights = highlights.filter((h) => h.anchor_type === "pdf");
    
    for (const h of pdfHighlights) {
      // PDF highlights must have page number and char offset
      if (h.pdf_page_number == null || h.pdf_char_offset == null) {
        if (process.env.NODE_ENV === "development") {
          console.warn(
            `[PdfReader] PDF highlight ${h.id} missing pdf_page_number or pdf_char_offset`
          );
        }
        continue;
      }

      const pageNumber = h.pdf_page_number;
      const pageRange = pageOffsetRanges.find((r) => r.pageNumber === pageNumber);
      
      if (!pageRange) {
        // Page not rendered yet (lazy loading); skip for now
        continue;
      }

      // Convert per-page offset to global offset
      // pdf_char_offset is the offset within the page
      // Global offset = page start offset + per-page offset
      const globalCharStart = pageRange.minOffset + h.pdf_char_offset;
      const globalCharEnd = globalCharStart + h.quote.length;

      // Sanity check: don't exceed page bounds
      if (globalCharEnd > pageRange.maxOffset) {
        if (process.env.NODE_ENV === "development") {
          console.warn(
            `[PdfReader] PDF highlight ${h.id} extends beyond page ${pageNumber} bounds`
          );
        }
      }

      const anchor: PdfHighlightAnchor = {
        highlightId: h.id,
        charStart: globalCharStart,
        charEnd: globalCharEnd,
        color: h.color,
        isActive: h.id === activeHighlightId,
      };

      const existing = byPage.get(pageNumber) || [];
      existing.push(anchor);
      byPage.set(pageNumber, existing);
    }
    
    return byPage;
  }, [highlights, pageOffsetRanges, activeHighlightId]);

  // Handle click on a highlight span
  const handleHighlightClick = useCallback(
    (highlightId: string) => {
      setActiveHighlightId(highlightId);
    },
    [setActiveHighlightId]
  );

  // Scroll to active highlight when it changes (triggered from inspector)
  useEffect(() => {
    if (!activeHighlightId || !containerRef.current) return;

    const element = findHighlightElement(containerRef.current, activeHighlightId);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeHighlightId]);

  // Load PDF document when buffer is available
  useEffect(() => {
    if (!pdfBuffer) return;

    let cancelled = false;

    async function loadPdf() {
      try {
        // Dynamic import to handle SSR and worker setup
        const pdfjsLib = await import("pdfjs-dist");

        // Configure worker from CDN to avoid Next.js/webpack bundling issues.
        // WORKER CONFIGURATION
        // 
        // The pdf.js worker file uses import.meta which Terser cannot handle when bundled.
        // Using unpkg CDN for the matching pdfjs-dist version as a workaround.
        //
        // TODO(hardening): Replace CDN worker with self-hosted worker before production.
        //   1. Copy pdf.worker.min.mjs to /public/pdf.worker.min.mjs
        //   2. Update workerSrc to "/pdf.worker.min.mjs"
        //   3. Add version pinning to avoid mismatches
        //   Benefits: Eliminates unpkg dependency, enables offline support, avoids CSP issues.
        //   See: spec/frontend.md § PDFs > Worker Configuration
        const pdfjsVersion = pdfjsLib.version;
        pdfjsLib.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjsVersion}/build/pdf.worker.min.mjs`;

        const loadingTask = pdfjsLib.getDocument({ data: pdfBuffer });
        const pdf = await loadingTask.promise;

        if (!cancelled) {
          setPdfDoc(pdf);
          setNumPages(pdf.numPages);
          globalCharOffset.current = 0;
        }
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to load PDF:", err);
          setLoadError(err instanceof Error ? err.message : "Failed to load PDF");
        }
      }
    }

    loadPdf();

    return () => {
      cancelled = true;
    };
  }, [pdfBuffer]);

  // Render pages when PDF is loaded
  useEffect(() => {
    if (!pdfDoc) return;

    // Capture pdfDoc in local variable to satisfy TypeScript null checks
    const pdf = pdfDoc;
    let cancelled = false;

    async function renderPages() {
      const pagesToRender = Math.min(renderedPageCount, numPages);
      const newPages: PageState[] = [];
      let charOffset = 0;

      for (let i = 1; i <= pagesToRender; i++) {
        if (cancelled) return;

        try {
          const page = await pdf.getPage(i);
          const viewport = page.getViewport({ scale: 1.5 });
          
          // Get text content for text layer
          const textContent = await page.getTextContent();
          const textItems: TextLayerItem[] = [];

          for (const item of textContent.items) {
            // Skip non-text items (e.g., marked content)
            if (!("str" in item)) continue;
            
            const textItem = item as PdfTextItem;
            if (!textItem.str) continue;

            // Get transform matrix for positioning
            const tx = textItem.transform;
            
            textItems.push({
              str: textItem.str,
              x: tx[4], // x position
              y: viewport.height - tx[5], // flip y for canvas coordinates
              width: textItem.width,
              height: textItem.height,
              fontSize: Math.sqrt(tx[0] * tx[0] + tx[1] * tx[1]),
              charOffset: charOffset,
            });

            charOffset += textItem.str.length;
          }

          newPages.push({
            pageNumber: i,
            textItems,
            width: viewport.width,
            height: viewport.height,
          });

          // Clean up page resources
          page.cleanup();
        } catch (err) {
          console.error(`Failed to render page ${i}:`, err);
        }
      }

      if (!cancelled) {
        setPages(newPages);
        globalCharOffset.current = charOffset;
      }
    }

    renderPages();

    return () => {
      cancelled = true;
    };
  }, [pdfDoc, numPages, renderedPageCount]);

  // Scroll detection to load more pages
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || renderedPageCount >= numPages) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && renderedPageCount < numPages) {
          setRenderedPageCount((prev) => Math.min(prev + PAGE_INCREMENT, numPages));
        }
      },
      {
        root: containerRef.current,
        rootMargin: "200px",
        threshold: 0,
      }
    );

    observer.observe(sentinel);

    return () => {
      observer.disconnect();
    };
  }, [renderedPageCount, numPages]);

  // Loading state (fetching blob)
  if (isLoading) {
    return (
      <div data-testid="pdf-reader-loading" className="flex justify-center items-center py-12">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-500 text-sm">Loading PDF...</p>
        </div>
      </div>
    );
  }

  // Error state (fetch error)
  if (isError) {
    return (
      <div data-testid="pdf-reader-error" className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-red-900 mb-2">Failed to load PDF</h2>
        <p className="text-red-700">{error?.message ?? "An unexpected error occurred"}</p>
      </div>
    );
  }

  // Error state (PDF parsing error)
  if (loadError) {
    return (
      <div data-testid="pdf-reader-error" className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-red-900 mb-2">Failed to parse PDF</h2>
        <p className="text-red-700">{loadError}</p>
      </div>
    );
  }

  // Loading state (parsing PDF)
  if (!pdfDoc || pages.length === 0) {
    return (
      <div data-testid="pdf-reader-loading" className="flex justify-center items-center py-12">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-500 text-sm">Preparing PDF viewer...</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      data-testid="pdf-reader"
      className="pdf-reader overflow-y-auto max-h-[calc(100vh-200px)]"
    >
      {/* Page count info */}
      <div className="mb-4 text-sm text-gray-500">
        Showing {pages.length} of {numPages} pages
      </div>

      {/* Rendered pages */}
      {pages.map((page) => (
        <PdfPage
          key={page.pageNumber}
          pageNumber={page.pageNumber}
          pdfDoc={pdfDoc}
          width={page.width}
          height={page.height}
          textItems={page.textItems}
          highlights={highlightsByPage.get(page.pageNumber) || []}
          activeHighlightId={activeHighlightId}
          onHighlightClick={handleHighlightClick}
        />
      ))}

      {/* Sentinel for infinite scroll */}
      {renderedPageCount < numPages && (
        <div
          ref={sentinelRef}
          className="h-20 flex items-center justify-center text-gray-400 text-sm"
        >
          <div className="inline-block animate-spin rounded-full h-5 w-5 border-b-2 border-gray-400 mr-2"></div>
          Loading more pages...
        </div>
      )}
    </div>
  );
}

/**
 * Props for individual PDF page component.
 */
interface PdfPageProps {
  pageNumber: number;
  pdfDoc: PDFDocumentProxy;
  width: number;
  height: number;
  textItems: TextLayerItem[];
  /** Highlights to render on this page */
  highlights: PdfHighlightAnchor[];
  /** Currently active highlight ID */
  activeHighlightId: string | null;
  /** Callback when a highlight is clicked */
  onHighlightClick: (highlightId: string) => void;
}

/**
 * Individual PDF page with canvas and text layer.
 */
function PdfPage({
  pageNumber,
  pdfDoc,
  width,
  height,
  textItems,
  highlights,
  activeHighlightId,
  onHighlightClick,
}: PdfPageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [isRendered, setIsRendered] = useState(false);

  // Render canvas when component mounts
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || isRendered) return;

    // Capture canvas in local variable to satisfy TypeScript null checks
    const canvasEl = canvas;
    let cancelled = false;

    async function renderCanvas() {
      try {
        const page = await pdfDoc.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.5 });

        const ctx = canvasEl.getContext("2d");
        if (!ctx || cancelled) return;

        canvasEl.width = viewport.width;
        canvasEl.height = viewport.height;

        await page.render({
          canvas: canvasEl,
          viewport,
        }).promise;

        if (!cancelled) {
          setIsRendered(true);
        }

        page.cleanup();
      } catch (err) {
        console.error(`Failed to render canvas for page ${pageNumber}:`, err);
      }
    }

    renderCanvas();

    return () => {
      cancelled = true;
    };
  }, [pdfDoc, pageNumber, isRendered]);

  // Apply highlights to the text layer after rendering
  useEffect(() => {
    const textLayer = textLayerRef.current;
    if (!textLayer || highlights.length === 0) return;

    // Clear existing highlights before re-applying
    clearPdfHighlightsFromPage(textLayer);

    // Apply highlights with current active state
    const anchorsWithActiveState = highlights.map((h) => ({
      ...h,
      isActive: h.highlightId === activeHighlightId,
    }));

    applyPdfHighlightsToPage(textLayer, anchorsWithActiveState);
  }, [highlights, activeHighlightId]);

  // Handle click events on the text layer (delegate to highlight spans)
  const handleTextLayerClick = useCallback(
    (e: React.MouseEvent) => {
      const target = e.target as HTMLElement;
      const highlightId = target.getAttribute("data-highlight-id");
      if (highlightId) {
        onHighlightClick(highlightId);
      }
    },
    [onHighlightClick]
  );

  return (
    <div
      className="pdf-page relative mb-4 shadow-lg bg-white"
      data-page-number={pageNumber}
      data-testid={`pdf-page-${pageNumber}`}
      style={{ width, height }}
    >
      {/* Canvas layer for rendering PDF visuals */}
      <canvas
        ref={canvasRef}
        className="block"
        data-testid={`pdf-canvas-${pageNumber}`}
      />

      {/* Text layer for selection and highlight anchoring */}
      <div
        ref={textLayerRef}
        className="pdf-text-layer absolute top-0 left-0 right-0 bottom-0 overflow-hidden pointer-events-none"
        style={{ width, height }}
        data-testid={`pdf-text-layer-${pageNumber}`}
        onClick={handleTextLayerClick}
      >
        {textItems.map((item, idx) => (
          <span
            key={`${pageNumber}-${idx}`}
            data-page-number={pageNumber}
            data-char-offset={item.charOffset}
            className="absolute whitespace-pre text-transparent select-text pointer-events-auto"
            style={{
              left: item.x,
              top: item.y - item.fontSize,
              fontSize: item.fontSize,
              // Approximate width/height for positioning
              lineHeight: `${item.fontSize}px`,
            }}
          >
            {item.str}
          </span>
        ))}
      </div>
    </div>
  );
}

