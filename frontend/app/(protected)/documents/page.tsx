"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchDocumentsList, isClientError, type ClientError } from "@/lib/api/documents";
import type { DocumentListItem } from "@/lib/generated-api";

/**
 * Documents list page.
 *
 * Displays a paginated table of user's documents with:
 * - Loading state
 * - Error state with retry
 * - Empty state
 * - Infinite pagination via "Load More" button
 */
export default function DocumentsPage() {
  const {
    data,
    error,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
    refetch,
  } = useInfiniteQuery({
    queryKey: ["documents"],
    queryFn: async ({ pageParam }) => {
      return fetchDocumentsList({
        cursor: pageParam,
        limit: 20,
      });
    },
    getNextPageParam: (lastPage) => {
      return lastPage.has_more ? lastPage.next_cursor : undefined;
    },
    initialPageParam: undefined as string | undefined,
  });

  // Flatten all pages into a single documents array
  const documents = data?.pages.flatMap((page) => page.items) ?? [];

  const handleLoadMore = () => {
    if (hasNextPage && !isFetchingNextPage) {
      void fetchNextPage();
    }
  };

  const handleRetry = () => {
    void refetch();
  };

  // Initial loading state
  if (isLoading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600">Loading documents...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    const clientError = isClientError(error) ? error : null;
    const errorMessage = clientError?.message ?? "An unexpected error occurred";

    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-red-900 mb-2">Failed to load documents</h2>
        <p className="text-red-700 mb-4">{errorMessage}</p>
        {clientError?.code && (
          <p className="text-red-600 text-sm mb-4">Error code: {clientError.code}</p>
        )}
        <button
          onClick={handleRetry}
          className="bg-red-600 text-white px-4 py-2 rounded font-medium hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  // Empty state
  if (documents.length === 0) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">No documents yet</h2>
        <p className="text-gray-600 mb-6">Upload your first document to get started</p>
      </div>
    );
  }

  // Success state with documents
  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Documents</h1>

      <div className="overflow-x-auto bg-white rounded-lg shadow">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Title</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Type</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
              <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Created</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {documents.map((doc) => (
              <tr
                key={doc.id}
                className="hover:bg-gray-50 cursor-pointer transition-colors"
                onClick={() => {
                  window.location.href = `/app/documents/${doc.id}`;
                }}
              >
                <td className="px-6 py-4 text-sm font-medium text-blue-600 hover:text-blue-800">
                  {doc.title || "(Untitled)"}
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">{doc.source_kind.toUpperCase()}</td>
                <td className="px-6 py-4 text-sm">
                  <StatusBadge status={doc.processing_status} />
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">{formatDate(doc.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasNextPage && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={handleLoadMore}
            disabled={isFetchingNextPage}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isFetchingNextPage ? "Loading..." : "Load More"}
          </button>
        </div>
      )}
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

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
