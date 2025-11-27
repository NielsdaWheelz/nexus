/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from "../core/CancelablePromise";
import { OpenAPI } from "../core/OpenAPI";
import { request as __request } from "../core/request";
export class TestService {
  /**
   * Test Rate Limited Endpoint
   * Test endpoint for anonymous rate limiting.
   *
   * This endpoint is rate-limited per IP (GLOBAL_ANON scope).
   * It's used for testing the rate limiting behavior without authentication.
   *
   * WARNING: Test-only endpoint. Should not be exposed in production.
   *
   * Returns:
   * JSON object confirming the request was allowed
   * @returns string Successful Response
   * @throws ApiError
   */
  public static testRateLimitedEndpointTestRateLimitedGet(): CancelablePromise<
    Record<string, string>
  > {
    return __request(OpenAPI, {
      method: "GET",
      url: "/test/rate-limited",
    });
  }
}
