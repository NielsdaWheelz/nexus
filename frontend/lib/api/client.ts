"use client";

import { OpenAPI } from "@/lib/generated-api";
import { useAuth } from "@clerk/nextjs";
import { useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Initialize OpenAPI client with base URL and auth headers.
 * Must be called once at app startup to configure the client.
 */
export function initializeApiClient(token: string | null) {
  OpenAPI.BASE = API_URL;
  OpenAPI.TOKEN = token || undefined;

  // Configure to use Bearer token format
  if (token) {
    OpenAPI.HEADERS = {
      ...OpenAPI.HEADERS,
      Authorization: `Bearer ${token}`,
    };
  }
}

/**
 * Hook to configure the API client with auth token.
 * Call this once in the app root to set up authentication.
 */
export function useApiClientSetup() {
  const { getToken } = useAuth();

  useEffect(() => {
    (async () => {
      const token = await getToken();
      initializeApiClient(token);
    })();
  }, [getToken]);
}

export * from "@/lib/generated-api";
