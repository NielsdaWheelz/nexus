/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CreateReaderRequest } from '../models/CreateReaderRequest';
import type { DataEnvelope_ReaderResponse_ } from '../models/DataEnvelope_ReaderResponse_';
import type { UpdateReaderRequest } from '../models/UpdateReaderRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ReadersService {
    /**
     * Create or retrieve reading session
     * Create a new reading session for a document, or return existing session if already created.
     * @param requestBody
     * @param authorization
     * @returns DataEnvelope_ReaderResponse_ Successful Response
     * @throws ApiError
     */
    public static createReaderReadersPost(
        requestBody: CreateReaderRequest,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_ReaderResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/readers',
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
     * Get reading session
     * Retrieve a reading session by ID.
     * @param readerId
     * @param authorization
     * @returns DataEnvelope_ReaderResponse_ Successful Response
     * @throws ApiError
     */
    public static getReaderReadersReaderIdGet(
        readerId: string,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_ReaderResponse_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/readers/{reader_id}',
            path: {
                'reader_id': readerId,
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
     * Update reading position
     * Update the current reading position in a document.
     * @param readerId
     * @param requestBody
     * @param authorization
     * @returns DataEnvelope_ReaderResponse_ Successful Response
     * @throws ApiError
     */
    public static updateReaderReadersReaderIdPatch(
        readerId: string,
        requestBody: UpdateReaderRequest,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_ReaderResponse_> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/readers/{reader_id}',
            path: {
                'reader_id': readerId,
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
}
