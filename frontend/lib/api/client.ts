"use client";

import { OpenAPI } from "@/lib/generated-api";
import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Configure the global OpenAPI client with base URL and Clerk-derived Bearer token.
 * This is the single source of truth for all OpenAPI client requests.
 *
 * The TOKEN resolver ensures that:
 * - The token is fetched fresh on each API request
 * - Token expiration is handled transparently by Clerk
 * - All service methods use the same authentication
 */
export function useConfigureOpenApiClient() {
  const { getToken } = useAuth();

  useEffect(() => {
    // Set the base URL once
    OpenAPI.BASE = API_URL;

    // Configure TOKEN as an async resolver
    // This ensures every API request gets a fresh, valid token from Clerk
    // The resolver must return a Promise<string>, never undefined
    OpenAPI.TOKEN = async () => {
      const token = await getToken();
      return token ?? "";
    };

    // Enable credentials for cross-origin requests
    OpenAPI.WITH_CREDENTIALS = true;
  }, [getToken]);
}

export * from "@/lib/generated-api";
