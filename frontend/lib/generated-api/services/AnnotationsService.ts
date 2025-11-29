/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreateAnnotationRequest } from '../models/CreateAnnotationRequest';
import type { DataEnvelope_AnnotationItem_ } from '../models/DataEnvelope_AnnotationItem_';
import type { DataEnvelope_AnnotationListResponse_ } from '../models/DataEnvelope_AnnotationListResponse_';
import type { UpdateAnnotationRequest } from '../models/UpdateAnnotationRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AnnotationsService {
    /**
     * Create annotation
     * Create a new annotation on a highlight.
     * @param requestBody
     * @param authorization
     * @returns DataEnvelope_AnnotationItem_ Successful Response
     * @throws ApiError
     */
    public static createAnnotationEndpointAnnotationsPost(
        requestBody: CreateAnnotationRequest,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_AnnotationItem_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/annotations',
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
     * Update annotation
     * Update an annotation's content.
     * @param annotationId Typed annotation ID (ann_<uuid>)
     * @param authorization
     * @param requestBody
     * @returns DataEnvelope_AnnotationItem_ Successful Response
     * @throws ApiError
     */
    public static updateAnnotationEndpointAnnotationsAnnotationIdPatch(
        annotationId: string,
        authorization?: (string | null),
        requestBody?: UpdateAnnotationRequest,
    ): CancelablePromise<DataEnvelope_AnnotationItem_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/annotations/{annotation_id}',
            path: {
                'annotation_id': annotationId,
            },
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
     * Delete annotation
     * Delete an annotation (soft delete).
     * @param annotationId Typed annotation ID (ann_<uuid>)
     * @param authorization
     * @returns void
     * @throws ApiError
     */
    public static deleteAnnotationEndpointAnnotationsAnnotationIdDelete(
        annotationId: string,
        authorization?: (string | null),
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/annotations/{annotation_id}',
            path: {
                'annotation_id': annotationId,
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
     * List annotations for document
     * List all annotations on a specific document owned by current user.
     * @param documentId Typed document ID (doc_<uuid>)
     * @param limit Results per page
     * @param cursor Pagination cursor from previous response
     * @param authorization
     * @returns DataEnvelope_AnnotationListResponse_ Successful Response
     * @throws ApiError
     */
    public static listDocumentAnnotationsDocumentsDocumentIdAnnotationsGet(
        documentId: string,
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_AnnotationListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/documents/{document_id}/annotations',
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
     * List annotations for highlight
     * List all annotations on a specific highlight.
     * @param highlightId Typed highlight ID (hl_<uuid>)
     * @param limit Results per page
     * @param cursor Pagination cursor from previous response
     * @param authorization
     * @returns DataEnvelope_AnnotationListResponse_ Successful Response
     * @throws ApiError
     */
    public static listHighlightAnnotationsHighlightsHighlightIdAnnotationsGet(
        highlightId: string,
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_AnnotationListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/highlights/{highlight_id}/annotations',
            path: {
                'highlight_id': highlightId,
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
     * List user's annotations
     * List all annotations created by a user.
     * @param userId Typed user ID (usr_<uuid>)
     * @param limit Results per page
     * @param cursor Pagination cursor from previous response
     * @param authorization
     * @returns DataEnvelope_AnnotationListResponse_ Successful Response
     * @throws ApiError
     */
    public static listUserAnnotationsUsersUserIdAnnotationsGet(
        userId: string,
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_AnnotationListResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/users/{user_id}/annotations',
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
