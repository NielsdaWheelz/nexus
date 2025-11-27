/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreateHighlightRequest } from "../models/CreateHighlightRequest";
import type { HighlightItem } from "../models/HighlightItem";
import type { HighlightListResponse } from "../models/HighlightListResponse";
import type { CancelablePromise } from "../core/CancelablePromise";
import { OpenAPI } from "../core/OpenAPI";
import { request as __request } from "../core/request";
export class HighlightsService {
  /**
   * Create highlight
   * Create a new highlight with byte-range anchor on a document.
   * @param requestBody
   * @param authorization
   * @returns HighlightItem Successful Response
   * @throws ApiError
   */
  public static createHighlightEndpointHighlightsPost(
    requestBody: CreateHighlightRequest,
    authorization?: string | null
  ): CancelablePromise<HighlightItem> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/highlights",
      headers: {
        authorization: authorization,
      },
      body: requestBody,
      mediaType: "application/json",
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * List highlights for document
   * List all highlights on a specific document owned by current user.
   * @param documentId Typed document ID (doc_<uuid>)
   * @param limit Results per page
   * @param cursor Pagination cursor from previous response
   * @param authorization
   * @returns HighlightListResponse Successful Response
   * @throws ApiError
   */
  public static listDocumentHighlightsDocumentsDocumentIdHighlightsGet(
    documentId: string,
    limit: number = 20,
    cursor?: string | null,
    authorization?: string | null
  ): CancelablePromise<HighlightListResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/documents/{document_id}/highlights",
      path: {
        document_id: documentId,
      },
      headers: {
        authorization: authorization,
      },
      query: {
        limit: limit,
        cursor: cursor,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * List user's highlights
   * List all highlights created by a user across all documents.
   * @param userId Typed user ID (usr_<uuid>)
   * @param limit Results per page
   * @param cursor Pagination cursor from previous response
   * @param authorization
   * @returns HighlightListResponse Successful Response
   * @throws ApiError
   */
  public static listUserHighlightsUsersUserIdHighlightsGet(
    userId: string,
    limit: number = 20,
    cursor?: string | null,
    authorization?: string | null
  ): CancelablePromise<HighlightListResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/users/{user_id}/highlights",
      path: {
        user_id: userId,
      },
      headers: {
        authorization: authorization,
      },
      query: {
        limit: limit,
        cursor: cursor,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
