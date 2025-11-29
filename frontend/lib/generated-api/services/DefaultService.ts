/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DataEnvelope_HealthStatus_ } from '../models/DataEnvelope_HealthStatus_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Health
     * Health check endpoint.
     *
     * Returns 200 OK without authentication and is NOT rate-limited.
     * This endpoint is always available for health monitoring.
     *
     * Returns:
     * DataEnvelope wrapping HealthStatus with ok=True and status="healthy"
     * @returns DataEnvelope_HealthStatus_ Successful Response
     * @throws ApiError
     */
    public static healthHealthGet(): CancelablePromise<DataEnvelope_HealthStatus_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/health',
        });
    }
}
