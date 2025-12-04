/**
 * Annotations API wrapper.
 *
 * This module provides domain-specific functions for annotation operations.
 * All functions:
 * - Use the HTTP layer for consistent error handling
 * - Unwrap DataEnvelope responses
 * - Throw ClientError on failure
 *
 * Pages should use these functions instead of AnnotationsService directly.
 */

import { AnnotationsService } from "@/lib/generated-api";
import type {
  AnnotationItem,
  AnnotationListResponse,
  CreateAnnotationRequest,
  UpdateAnnotationRequest,
} from "@/lib/generated-api";
import { callApi } from "./http";

/**
 * Parameters for creating an annotation.
 */
export interface CreateAnnotationParams {
  /** Typed highlight ID (hl_<uuid>) */
  highlightId: string;
  /** Annotation text content */
  content: string;
}

/**
 * Parameters for updating an annotation.
 */
export interface UpdateAnnotationParams {
  /** Typed annotation ID (ann_<uuid>) */
  annotationId: string;
  /** Updated annotation text content */
  content: string;
}

/**
 * Response shape for annotations list.
 * This is the unwrapped inner content of DataEnvelope<AnnotationListResponse>.
 */
export interface AnnotationsListResult {
  items: AnnotationItem[];
  next_cursor: string | null;
  has_more: boolean;
}

/**
 * Fetch paginated list of annotations for a highlight.
 *
 * @param highlightId - The highlight ID to fetch annotations for
 * @param cursor - Pagination cursor (undefined for first page)
 * @param limit - Number of items per page (default: 100)
 * @returns Unwrapped list result with items, cursor, and has_more
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const result = await listAnnotationsForHighlight("hl_abc123...");
 * console.log(result.items); // AnnotationItem[]
 * console.log(result.has_more); // boolean
 * ```
 */
export async function listAnnotationsForHighlight(
  highlightId: string,
  cursor?: string | null,
  limit: number = 100
): Promise<AnnotationsListResult> {
  const response = await callApi<AnnotationListResponse>(() =>
    AnnotationsService.listHighlightAnnotationsHighlightsHighlightIdAnnotationsGet(
      highlightId,
      limit,
      cursor ?? undefined
    )
  );

  return {
    items: response.items,
    next_cursor: response.next_cursor ?? null,
    has_more: response.has_more,
  };
}

/**
 * Create a new annotation on a highlight.
 *
 * @param params - Highlight ID and annotation content
 * @returns The created annotation item
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const annotation = await createAnnotation({
 *   highlightId: "hl_abc123...",
 *   content: "This is an important passage.",
 * });
 * console.log(annotation.id); // "ann_xyz..."
 * ```
 */
export async function createAnnotation(
  params: CreateAnnotationParams
): Promise<AnnotationItem> {
  const request: CreateAnnotationRequest = {
    highlight_id: params.highlightId,
    content: params.content,
  };

  const response = await callApi<AnnotationItem>(() =>
    AnnotationsService.createAnnotationEndpointAnnotationsPost(request)
  );

  return response;
}

/**
 * Update an existing annotation's content.
 *
 * @param params - Annotation ID and new content
 * @returns The updated annotation item
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * const annotation = await updateAnnotation({
 *   annotationId: "ann_xyz123...",
 *   content: "Updated note text.",
 * });
 * ```
 */
export async function updateAnnotation(
  params: UpdateAnnotationParams
): Promise<AnnotationItem> {
  const request: UpdateAnnotationRequest = {
    content: params.content,
  };

  const response = await callApi<AnnotationItem>(() =>
    AnnotationsService.updateAnnotationEndpointAnnotationsAnnotationIdPatch(
      params.annotationId,
      undefined,
      request
    )
  );

  return response;
}

/**
 * Delete an annotation (soft delete).
 *
 * @param annotationId - The annotation ID to delete
 * @throws {ClientError} On API failure
 *
 * @example
 * ```ts
 * await deleteAnnotation("ann_xyz123...");
 * ```
 */
export async function deleteAnnotation(annotationId: string): Promise<void> {
  await callApi<void>(() =>
    AnnotationsService.deleteAnnotationEndpointAnnotationsAnnotationIdDelete(
      annotationId
    )
  );
}

// Re-export types for convenience
export type { AnnotationItem, AnnotationListResponse };

