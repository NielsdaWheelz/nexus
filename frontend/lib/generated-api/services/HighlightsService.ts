/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreateHighlightRequest } from '../models/CreateHighlightRequest';
import type { DataEnvelope_HighlightItem_ } from '../models/DataEnvelope_HighlightItem_';
import type { DataEnvelope_HighlightListResponse_ } from '../models/DataEnvelope_HighlightListResponse_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class HighlightsService {
    /**
     * Create highlight
     * Create a new highlight with byte-range anchor on a document.
     * @param requestBody
     * @param authorization
     * @returns DataEnvelope_HighlightItem_ Successful Response
     * @throws ApiError
     */
    public static createHighlightEndpointHighlightsPost(
        requestBody: CreateHighlightRequest,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_HighlightItem_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/highlights',
            headers: {
                'authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
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
     * @returns DataEnvelope_HighlightListResponse_ Successful Response
     * @throws ApiError
     */
    public static listDocumentHighlightsDocumentsDocumentIdHighlightsGet(
        documentId: string,
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_HighlightListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/documents/{document_id}/highlights',
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
    /**
     * List user's highlights
     * List all highlights created by a user across all documents.
     * @param userId Typed user ID (usr_<uuid>)
     * @param limit Results per page
     * @param cursor Pagination cursor from previous response
     * @param authorization
     * @returns DataEnvelope_HighlightListResponse_ Successful Response
     * @throws ApiError
     */
    public static listUserHighlightsUsersUserIdHighlightsGet(
        userId: string,
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_HighlightListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/users/{user_id}/highlights',
            path: {
                'user_id': userId,
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
