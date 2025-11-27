import { PaginatedResponse } from "../api-client";

export interface DocumentListItem {
  id: string; // doc_<uuid>
  title: string | null;
  source_kind: "pdf" | "epub" | "html";
  processing_status: "pending" | "processing" | "ready" | "failed";
  created_at: string; // ISO8601
  updated_at: string; // ISO8601
}

export interface DocumentListResponse extends PaginatedResponse<DocumentListItem> {}

/**
 * Build query parameters for document list endpoint
 */
export function buildDocumentsQuery(
  cursor?: string | null,
  limit = 20,
  status?: string
): string {
  const params = new URLSearchParams();
  if (cursor) {
    params.set("cursor", cursor);
  }
  params.set("limit", limit.toString());
  if (status) {
    params.set("status", status);
  }

  const queryString = params.toString();
  return `/documents${queryString ? `?${queryString}` : ""}`;
}
