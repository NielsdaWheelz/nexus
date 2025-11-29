"use client";

/**
 * API client configuration.
 *
 * This module provides functions to configure the OpenAPI client with
 * authentication tokens from Clerk. It ensures proper integration with
 * React's component lifecycle.
 *
 * Usage:
 * - Use `useConfigureOpenApiClient()` hook in a client component
 *   that wraps your app (e.g., protected layout)
 * - Or call `configureApiClient()` with a getToken function
 */

import { OpenAPI } from "@/lib/generated-api";
import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Configure the OpenAPI client with a token resolver function.
 *
 * This function is the low-level configuration API. It sets up:
 * - Base URL for API requests
 * - Token resolver for Bearer authentication
 * - Credentials mode for cross-origin requests
 *
 * @param getToken - Async function that returns the current auth token (or null)
 *
 * @example
 * ```tsx
 * // In a React component:
 * const { getToken } = useAuth();
 *
 * useEffect(() => {
 *   configureApiClient(getToken);
 * }, [getToken]);
 * ```
 */
export function configureApiClient(getToken: () => Promise<string | null>): void {
  // Set the base URL
  OpenAPI.BASE = API_URL;

  // Configure TOKEN as an async resolver
  // This ensures every API request gets a fresh, valid token from Clerk
  OpenAPI.TOKEN = async () => {
    const token = await getToken();
    return token ?? "";
  };

  // Enable credentials for cross-origin requests
  OpenAPI.WITH_CREDENTIALS = true;
}

/**
 * React hook to configure the OpenAPI client with Clerk auth.
 *
 * This hook should be called once in a component that wraps your app
 * (e.g., the protected layout). It automatically sets up the token
 * resolver using Clerk's useAuth hook.
 *
 * The hook ensures:
 * - Token is fetched fresh on each API request
 * - Token expiration is handled transparently by Clerk
 * - All service methods use the same authentication
 *
 * @example
 * ```tsx
 * // In app/(protected)/layout.tsx:
 * export default function ProtectedLayout({ children }) {
 *   useConfigureOpenApiClient();
 *   return <div>{children}</div>;
 * }
 * ```
 */
export function useConfigureOpenApiClient(): void {
  const { getToken } = useAuth();
  const configuredRef = useRef(false);

  useEffect(() => {
    // Configure the client with the getToken function
    configureApiClient(getToken);
    configuredRef.current = true;
  }, [getToken]);
}

// Re-export types and utilities that pages might need
export type { ClientError } from "./http";
export { isAuthError, isNotFoundError, isClientError } from "./http";
