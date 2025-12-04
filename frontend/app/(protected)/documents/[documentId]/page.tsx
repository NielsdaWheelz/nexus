"use client";

import { useCallback } from "react";
import Link from "next/link";
import { useDocumentDetail } from "@/lib/hooks/useDocuments";
import { useDocumentHighlights } from "@/lib/hooks/useHighlights";
import { useDocumentContent } from "@/lib/hooks/useDocumentContent";
import { isClientError, isNotFoundError, type ClientError } from "@/lib/api/http";
import { DocumentListItem } from "@/lib/generated-api";
import { ReaderLayout } from "@/components/reader/ReaderLayout";
import { HtmlHighlightReader } from "@/components/reader/HtmlHighlightReader";
import { PdfReader } from "@/components/reader/PdfReader";
import { InspectorPanel } from "@/components/inspector/InspectorPanel";
import { AnnotationsInspectorTab } from "@/components/reader/AnnotationsInspectorTab";
import { useUIStore } from "@/lib/state/ui";

/**
 * Document detail page.
 *
 * Displays document in a 3-pane reader layout with:
 * - Left: Navigation (placeholder)
 * - Center: Document metadata (future: reader content)
 * - Right: Inspector panel with tabs
 */
export default function DocumentDetailPage({ params }: { params: { documentId: string } }) {
  const { data: document, error, isLoading } = useDocumentDetail(params.documentId);

  // Loading state
  if (isLoading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading document...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    const clientError: ClientError | null = isClientError(error) ? error : null;
    const isNotFound = clientError ? isNotFoundError(clientError) : false;

    return (
      <div>
        <Link
          href="/app/documents"
          className="text-blue-600 hover:text-blue-800 font-medium mb-6 inline-block"
        >
          ← Back to documents
        </Link>
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-red-900 mb-2">
            {isNotFound ? "Document not found" : "Failed to load document"}
          </h2>
          <p className="text-red-700">
            {isNotFound
              ? "The document you're looking for doesn't exist or you don't have access to it."
              : clientError?.message ?? "An unexpected error occurred"}
          </p>
          {clientError?.code && !isNotFound && (
            <p className="text-red-600 text-sm mt-2">Error code: {clientError.code}</p>
          )}
        </div>
      </div>
    );
  }

  // No document (shouldn't happen if no error, but handle defensively)
  if (!document) {
    return null;
  }

  // Success state: render in ReaderLayout
  return (
    <DocumentReader document={document} documentId={params.documentId} />
  );
}

/**
 * Document reader wrapper that handles highlights and content rendering.
 *
 * This component:
 * 1. Fetches highlights and content for the document
 * 2. Owns the activeHighlightId state (via UI store)
 * 3. Wires the InspectorPanel click handler to set activeHighlightId
 * 4. Passes activeHighlightId to the reader (which handles scrolling)
 *
 * The readers (HtmlHighlightReader, PdfReader) react to activeHighlightId
 * changes from the store and scroll to the corresponding highlight.
 */
function DocumentReader({
  document,
  documentId,
}: {
  document: DocumentListItem;
  documentId: string;
}) {
  const isReady = document.processing_status === "ready";

  // UI store for active/hovered highlight state
  // Readers (HtmlHighlightReader, PdfReader) subscribe to activeHighlightId
  // and scroll to the highlight when it changes.
  const activeHighlightId = useUIStore((s) => s.activeHighlightId);
  const hoveredHighlightId = useUIStore((s) => s.hoveredHighlightId);
  const setActiveHighlightId = useUIStore((s) => s.setActiveHighlightId);
  const setHoveredHighlightId = useUIStore((s) => s.setHoveredHighlightId);

  // Fetch highlights for this document
  const {
    highlights,
    isLoading: highlightsLoading,
    isError: highlightsError,
    error: highlightsErrorObj,
  } = useDocumentHighlights(documentId, {
    enabled: isReady,
  });

  // Fetch canonical text content
  const {
    data: contentData,
    isLoading: contentLoading,
    isError: contentError,
    error: contentErrorObj,
  } = useDocumentContent(documentId, {
    enabled: isReady,
  });

  // Check document type
  const isPdfDocument = document.source_kind === DocumentListItem.source_kind.PDF;
  const isTextDocument =
    document.source_kind === DocumentListItem.source_kind.HTML ||
    document.source_kind === DocumentListItem.source_kind.EPUB;

  const canonicalText = contentData?.canonical_text ?? null;

  // Handle highlight click from inspector
  // Sets the activeHighlightId in the store, which triggers the reader to scroll
  const handleHighlightClick = useCallback(
    (highlightId: string) => {
      setActiveHighlightId(highlightId);
    },
    [setActiveHighlightId]
  );

  // Handle highlight hover from inspector
  const handleHighlightHover = useCallback(
    (highlightId: string | null) => {
      setHoveredHighlightId(highlightId);
    },
    [setHoveredHighlightId]
  );

  // Build inspector content for highlights tab using unified InspectorPanel
  const highlightsContent = (
    <InspectorPanel
      documentId={documentId}
      highlights={highlights}
      isLoading={highlightsLoading}
      error={highlightsError ? highlightsErrorObj?.message : null}
      activeHighlightId={activeHighlightId}
      hoveredHighlightId={hoveredHighlightId}
      onHighlightClick={handleHighlightClick}
      onHighlightHover={handleHighlightHover}
    />
  );

  // Build inspector content for annotations tab
  const annotationsContent = (
    <AnnotationsInspectorTab highlightId={activeHighlightId} />
  );

  // Determine reader content based on document type and status
  let readerContent: React.ReactNode;

  if (document.processing_status !== "ready") {
    // Document not ready yet
    readerContent = <DocumentContent document={document} />;
  } else if (isPdfDocument) {
    // PDF document - use PdfReader (read-only for now)
    readerContent = (
      <PdfReader documentId={documentId} document={document} />
    );
  } else if (!isTextDocument) {
    // Unknown document type
    readerContent = (
      <div className="bg-gray-50 rounded-lg border border-gray-200 p-8 text-center">
        <h2 className="text-lg font-semibold text-gray-700 mb-2">
          Unsupported Document Type
        </h2>
        <p className="text-gray-500">
          This document type is not yet supported.
        </p>
        <DocumentContent document={document} />
      </div>
    );
  } else if (contentLoading) {
    // Loading content
    readerContent = (
      <div className="flex justify-center items-center py-12">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-500 text-sm">Loading document content...</p>
        </div>
      </div>
    );
  } else if (contentError) {
    // Error loading content
    readerContent = (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-red-900 mb-2">
          Failed to load content
        </h2>
        <p className="text-red-700">
          {contentErrorObj?.message ?? "An unexpected error occurred"}
        </p>
        <DocumentContent document={document} />
      </div>
    );
  } else if (!canonicalText) {
    // Text document but no content available
    readerContent = (
      <div>
        <DocumentContent document={document} />
        <div className="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-yellow-800 mb-1">
            No Content Available
          </h3>
          <p className="text-sm text-yellow-700">
            This document has no extractable text content.
          </p>
        </div>
      </div>
    );
  } else {
    // Render the document with highlights
    readerContent = (
      <HtmlHighlightReader
        canonicalText={canonicalText}
        highlights={highlights}
        documentId={documentId}
      />
    );
  }

  return (
    <ReaderLayout
      documentId={documentId}
      highlightsContent={highlightsContent}
      annotationsContent={annotationsContent}
    >
      {readerContent}
    </ReaderLayout>
  );
}

/**
 * Document content for the center pane.
 */
function DocumentContent({ document }: { document: DocumentListItem }) {
  return (
    <div>
      <Link
        href="/app/documents"
        className="text-blue-600 hover:text-blue-800 font-medium mb-4 inline-block text-sm"
      >
        ← Back to documents
      </Link>

      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <h1 className="text-2xl font-bold text-gray-900 mb-4">
          {document.title || "(Untitled)"}
        </h1>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Type</span>
            <p className="font-medium text-gray-900 mt-0.5">
              {document.source_kind.toUpperCase()}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Status</span>
            <p className="mt-0.5">
              <StatusBadge status={document.processing_status} />
            </p>
          </div>
          <div>
            <span className="text-gray-500">Created</span>
            <p className="font-medium text-gray-900 mt-0.5">
              {formatDateTime(document.created_at)}
            </p>
          </div>
          <div>
            <span className="text-gray-500">Updated</span>
            <p className="font-medium text-gray-900 mt-0.5">
              {formatDateTime(document.updated_at)}
            </p>
          </div>
          <div className="col-span-2">
            <span className="text-gray-500">ID</span>
            <p className="font-mono text-xs text-gray-900 mt-0.5 break-all">
              {document.id}
            </p>
          </div>
        </div>

        {document.processing_status === "processing" && (
          <div className="mt-6 bg-blue-50 border border-blue-200 p-4 rounded">
            <p className="text-blue-900 text-sm">
              This document is currently being processed. Please check back in a moment.
            </p>
          </div>
        )}

        {document.processing_status === "failed" && (
          <div className="mt-6 bg-red-50 border border-red-200 p-4 rounded">
            <p className="text-red-900 text-sm">
              This document failed to process. Please try uploading it again.
            </p>
          </div>
        )}

        {document.processing_status === "ready" && (
          <div className="mt-6 text-gray-400 text-sm">
            Document content preview coming soon.
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: DocumentListItem.processing_status }) {
  const colors = {
    pending: "bg-yellow-100 text-yellow-800",
    processing: "bg-blue-100 text-blue-800",
    ready: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${colors[status]}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function formatDateTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
