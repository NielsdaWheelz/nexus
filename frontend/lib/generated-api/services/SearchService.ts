/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ChunkSearchRequest } from '../models/ChunkSearchRequest';
import type { DataEnvelope_ChunkSearchResponse_ } from '../models/DataEnvelope_ChunkSearchResponse_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SearchService {
    /**
     * Search document chunks
     * Search document content chunks by semantic similarity.
     * @param requestBody
     * @param authorization
     * @returns DataEnvelope_ChunkSearchResponse_ Successful Response
     * @throws ApiError
     */
    public static searchChunksSearchChunksPost(
        requestBody: ChunkSearchRequest,
        authorization?: (string | null),
    ): CancelablePromise<DataEnvelope_ChunkSearchResponse_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/search/chunks',
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
