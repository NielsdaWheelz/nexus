"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useApiRequest } from "@/lib/api-client";
import { DocumentListItem, DocumentListResponse, buildDocumentsQuery } from "@/lib/api/documents";

export default function DocumentsPage() {
  const { apiGet } = useApiRequest();
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchDocuments = async (cursor?: string | null) => {
    try {
      const endpoint = buildDocumentsQuery(cursor);
      const response = await apiGet<DocumentListResponse>(endpoint);

      if (cursor) {
        // Append to existing documents for pagination
        setDocuments((prev) => [...prev, ...response.items]);
      } else {
        // Replace documents for initial load
        setDocuments(response.items);
      }

      setNextCursor(response.next_cursor);
      setHasMore(response.has_more);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiGet]);

  const handleLoadMore = async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    await fetchDocuments(nextCursor);
  };

  const handleRetry = () => {
    setLoading(true);
    setError(null);
    setDocuments([]);
    setNextCursor(null);
    fetchDocuments();
  };

  if (loading && documents.length === 0) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading documents...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-red-900 mb-2">
          Failed to load documents
        </h2>
        <p className="text-red-700 mb-4">{error}</p>
        <button
          onClick={handleRetry}
          className="bg-red-600 text-white px-4 py-2 rounded font-medium hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">No documents yet</h2>
        <p className="text-gray-600 mb-6">
          Upload your first document to get started
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Documents</h1>

      <div className="overflow-x-auto bg-white rounded-lg shadow">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Title
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Type
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Status
              </th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">
                Created
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {documents.map((doc) => (
              <tr
                key={doc.id}
                className="hover:bg-gray-50 cursor-pointer transition-colors"
                onClick={() => {
                  // Navigate to document detail
                  window.location.href = `/app/documents/${doc.id}`;
                }}
              >
                <td className="px-6 py-4 text-sm font-medium text-blue-600 hover:text-blue-800">
                  {doc.title || "(Untitled)"}
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">
                  {doc.source_kind.toUpperCase()}
                </td>
                <td className="px-6 py-4 text-sm">
                  <StatusBadge status={doc.processing_status} />
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">
                  {formatDate(doc.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={handleLoadMore}
            disabled={loadingMore}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loadingMore ? "Loading..." : "Load More"}
          </button>
        </div>
      )}
    </div>
  );
}

function StatusBadge({
  status,
}: {
  status: "pending" | "processing" | "ready" | "failed";
}) {
  const colors = {
    pending: "bg-yellow-100 text-yellow-800",
    processing: "bg-blue-100 text-blue-800",
    ready: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <span
      className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${colors[status]}`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
