"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ApiError {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
    trace_id?: string;
  };
}

export interface ApiResponse<T> {
  ok: true;
  data: T;
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}

/**
 * Hook for making authenticated API requests with Clerk JWT token
 */
export function useApiRequest() {
  const { getToken } = useAuth();

  const apiRequest = useCallback(
    async <T,>(endpoint: string, options?: RequestInit): Promise<T> => {
      const token = await getToken();

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(options?.headers as Record<string, string>),
      };

      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const url = `${API_URL}${endpoint}`;
      const response = await fetch(url, {
        ...options,
        headers,
      });

      const data = await response.json();

      if (!response.ok) {
        const error = data as ApiError;
        throw new Error(
          error.error?.message || `API error: ${response.status}`
        );
      }

      // Handle both paginated and regular responses
      if (
        data &&
        typeof data === "object" &&
        "items" in data &&
        "next_cursor" in data &&
        "has_more" in data
      ) {
        return data as T;
      }

      // If it's a direct response (not wrapped), return it
      return data as T;
    },
    [getToken]
  );

  const apiGet = useCallback(
    async <T,>(endpoint: string): Promise<T> => {
      return apiRequest<T>(endpoint, { method: "GET" });
    },
    [apiRequest]
  );

  const apiPost = useCallback(
    async <T,>(endpoint: string, body: unknown): Promise<T> => {
      return apiRequest<T>(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
    [apiRequest]
  );

  const apiPatch = useCallback(
    async <T,>(endpoint: string, body: unknown): Promise<T> => {
      return apiRequest<T>(endpoint, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    },
    [apiRequest]
  );

  const apiDelete = useCallback(
    async (endpoint: string): Promise<void> => {
      return apiRequest<void>(endpoint, { method: "DELETE" });
    },
    [apiRequest]
  );

  return { apiGet, apiPost, apiPatch, apiDelete };
}
