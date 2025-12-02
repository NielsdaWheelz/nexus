/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_document_documents_post } from '../models/Body_upload_document_documents_post';
import type { DataEnvelope_DocumentContentResponse_ } from '../models/DataEnvelope_DocumentContentResponse_';
import type { DataEnvelope_DocumentListItem_ } from '../models/DataEnvelope_DocumentListItem_';
import type { DataEnvelope_DocumentListResponse_ } from '../models/DataEnvelope_DocumentListResponse_';
import type { DataEnvelope_DocumentUploadResponse_ } from '../models/DataEnvelope_DocumentUploadResponse_';
import type { DataEnvelope_ReaderListResponse_ } from '../models/DataEnvelope_ReaderListResponse_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DocumentsService {
    /**
     * Upload document
     * Upload a document file and create a placeholder for ingestion.
     * @param formData
     * @param authorization
     * @returns DataEnvelope_DocumentUploadResponse_ Successful Response
     * @throws ApiError
     */
    public static uploadDocumentDocumentsPost(
        formData: Body_upload_document_documents_post,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_DocumentUploadResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/documents',
            headers: {
                'authorization': authorization,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
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
     * @returns DataEnvelope_DocumentListResponse_ Successful Response
     * @throws ApiError
     */
    public static listDocumentsDocumentsGet(
        status?: (string | null),
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_DocumentListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/documents',
            headers: {
                'authorization': authorization,
            },
            query: {
                'status': status,
                'limit': limit,
                'cursor': cursor,
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
     * @returns DataEnvelope_DocumentListItem_ Successful Response
     * @throws ApiError
     */
    public static getDocumentDocumentsDocumentIdGet(
        documentId: string,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_DocumentListItem_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/documents/{document_id}',
            path: {
                'document_id': documentId,
            },
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get document content
     * Retrieve the canonical text content of a document for rendering.
     * @param documentId
     * @param authorization
     * @returns DataEnvelope_DocumentContentResponse_ Successful Response
     * @throws ApiError
     */
    public static getDocumentContentDocumentsDocumentIdContentGet(
        documentId: string,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_DocumentContentResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/documents/{document_id}/content',
            path: {
                'document_id': documentId,
            },
            headers: {
                'authorization': authorization,
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
     * @returns DataEnvelope_ReaderListResponse_ Successful Response
     * @throws ApiError
     */
    public static listDocumentReadersDocumentsDocumentIdReadersGet(
        documentId: string,
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_ReaderListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/documents/{document_id}/readers',
            path: {
                'document_id': documentId,
            },
            headers: {
                'authorization': authorization,
            },
            query: {
                'limit': limit,
                'cursor': cursor,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
