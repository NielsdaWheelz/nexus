"use client";

import Link from "next/link";
import { useDocumentDetail } from "@/lib/hooks/useDocuments";
import { isClientError, isNotFoundError, type ClientError } from "@/lib/api/http";
import type { DocumentListItem } from "@/lib/generated-api";

/**
 * Document detail page.
 *
 * Displays full metadata for a single document with:
 * - Loading state
 * - Error state (including special handling for NOT_FOUND)
 * - Processing/failed status messages
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

  // Success state
  return (
    <div>
      <Link
        href="/app/documents"
        className="text-blue-600 hover:text-blue-800 font-medium mb-6 inline-block"
      >
        ← Back to documents
      </Link>

      <div className="bg-white rounded-lg shadow p-8 mb-8">
        <div className="mb-6">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            {document.title || "(Untitled)"}
          </h1>
          <div className="flex items-center gap-4 flex-wrap">
            <div>
              <span className="text-sm text-gray-600">Type:</span>
              <p className="text-lg font-medium text-gray-900">
                {document.source_kind.toUpperCase()}
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">Status:</span>
              <p className="mt-1">
                <StatusBadge status={document.processing_status} />
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">Created:</span>
              <p className="text-lg font-medium text-gray-900">
                {formatDateTime(document.created_at)}
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">Updated:</span>
              <p className="text-lg font-medium text-gray-900">
                {formatDateTime(document.updated_at)}
              </p>
            </div>
          </div>
        </div>

        <div className="border-t pt-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Document Details</h2>
          <div className="grid grid-cols-2 gap-8">
            <div>
              <h3 className="text-sm font-medium text-gray-600 mb-2">ID</h3>
              <p className="text-gray-900 font-mono text-sm break-all">{document.id}</p>
            </div>
            <div>
              <h3 className="text-sm font-medium text-gray-600 mb-2">Processing Status</h3>
              <p className="text-gray-900 capitalize">{document.processing_status}</p>
            </div>
          </div>
        </div>

        {document.processing_status === "ready" && (
          <div className="border-t mt-6 pt-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Document Content</h2>
            <p className="text-gray-600 text-sm mb-4">
              Document text preview and interaction features coming soon.
            </p>
          </div>
        )}

        {document.processing_status === "processing" && (
          <div className="border-t mt-6 pt-6 bg-blue-50 p-4 rounded">
            <p className="text-blue-900">
              This document is currently being processed. Please check back in a moment.
            </p>
          </div>
        )}

        {document.processing_status === "failed" && (
          <div className="border-t mt-6 pt-6 bg-red-50 p-4 rounded">
            <p className="text-red-900">
              This document failed to process. Please try uploading it again.
            </p>
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
    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${colors[status]}`}>
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
