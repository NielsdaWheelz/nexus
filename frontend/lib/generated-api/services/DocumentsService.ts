/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_document_documents_post } from "../models/Body_upload_document_documents_post";
import type { DocumentListItem } from "../models/DocumentListItem";
import type { DocumentListResponse } from "../models/DocumentListResponse";
import type { DocumentUploadResponse } from "../models/DocumentUploadResponse";
import type { ReaderListResponse } from "../models/ReaderListResponse";
import type { CancelablePromise } from "../core/CancelablePromise";
import { OpenAPI } from "../core/OpenAPI";
import { request as __request } from "../core/request";
export class DocumentsService {
  /**
   * Upload document
   * Upload a document file and create a placeholder for ingestion.
   * @param formData
   * @param authorization
   * @returns DocumentUploadResponse Successful Response
   * @throws ApiError
   */
  public static uploadDocumentDocumentsPost(
    formData: Body_upload_document_documents_post,
    authorization?: string | null
  ): CancelablePromise<DocumentUploadResponse> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/documents",
      headers: {
        authorization: authorization,
      },
      formData: formData,
      mediaType: "multipart/form-data",
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * List user's documents
   * Retrieve paginated list of authenticated user's documents.
   * @param status Optional status filter (pending, processing, ready, failed)
   * @param limit
   * @param cursor
   * @param authorization
   * @returns DocumentListResponse Successful Response
   * @throws ApiError
   */
  public static listDocumentsDocumentsGet(
    status?: string | null,
    limit: number = 20,
    cursor?: string | null,
    authorization?: string | null
  ): CancelablePromise<DocumentListResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/documents",
      headers: {
        authorization: authorization,
      },
      query: {
        status: status,
        limit: limit,
        cursor: cursor,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * Get document detail
   * Retrieve a single document by ID with full metadata.
   * @param documentId
   * @param authorization
   * @returns DocumentListItem Successful Response
   * @throws ApiError
   */
  public static getDocumentDocumentsDocumentIdGet(
    documentId: string,
    authorization?: string | null
  ): CancelablePromise<DocumentListItem> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/documents/{document_id}",
      path: {
        document_id: documentId,
      },
      headers: {
        authorization: authorization,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
  /**
   * List readers for document
   * List all reading sessions for a document with cursor pagination.
   * @param documentId
   * @param limit
   * @param cursor
   * @param authorization
   * @returns ReaderListResponse Successful Response
   * @throws ApiError
   */
  public static listDocumentReadersDocumentsDocumentIdReadersGet(
    documentId: string,
    limit: number = 20,
    cursor?: string | null,
    authorization?: string | null
  ): CancelablePromise<ReaderListResponse> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/documents/{document_id}/readers",
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
}
