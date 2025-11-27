/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from "../core/CancelablePromise";
import { OpenAPI } from "../core/OpenAPI";
import { request as __request } from "../core/request";
export class AuthService {
  /**
   * Get Current User Profile
   * Get current authenticated user profile.
   *
   * Returns user information for the authenticated user.
   * This endpoint is rate-limited per user (GLOBAL_USER scope).
   *
   * Args:
   * current_user: Authenticated user from rate-limited dependency
   *
   * Returns:
   * User profile with typed ID and metadata
   * @param authorization
   * @returns string Successful Response
   * @throws ApiError
   */
  public static getCurrentUserProfileAuthMeGet(
    authorization?: string | null
  ): CancelablePromise<Record<string, string>> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/auth/me",
      headers: {
        authorization: authorization,
      },
      errors: {
        422: `Validation Error`,
      },
    });
  }
}
