/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from "../core/CancelablePromise";
import { OpenAPI } from "../core/OpenAPI";
import { request as __request } from "../core/request";
export class DefaultService {
  /**
   * Health
   * Health check endpoint.
   *
   * Returns 200 OK without authentication and is NOT rate-limited.
   * This endpoint is always available for health monitoring.
   *
   * Returns:
   * JSON response with health status
   * @returns any Successful Response
   * @throws ApiError
   */
  public static healthHealthGet(): CancelablePromise<Record<string, boolean | string>> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/health",
    });
  }
}
