"use client";

import { UserButton } from "@clerk/nextjs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import Link from "next/link";
import { useState } from "react";
import { useConfigureOpenApiClient } from "@/lib/api/client";

/**
 * Create a stable QueryClient instance.
 *
 * Using useState ensures the QueryClient is only created once per component
 * lifecycle and survives re-renders. This is the recommended pattern for
 * Next.js App Router.
 */
function useQueryClient() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Don't refetch on window focus by default (can be noisy)
            refetchOnWindowFocus: false,
            // Retry failed requests once
            retry: 1,
            // Consider data stale after 30 seconds
            staleTime: 30 * 1000,
          },
        },
      })
  );
  return queryClient;
}

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  // Configure the OpenAPI client with Clerk auth token once when layout mounts
  useConfigureOpenApiClient();

  // Create stable QueryClient instance
  const queryClient = useQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-gray-50">
        <nav className="bg-white border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <div className="flex items-center">
                <Link href="/app" className="text-2xl font-bold text-gray-900">
                  Nexus
                </Link>
                <div className="ml-10 flex space-x-8">
                  <Link
                    href="/app/documents"
                    className="text-gray-700 hover:text-gray-900 font-medium"
                  >
                    Documents
                  </Link>
                  <Link
                    href="/app/upload"
                    className="text-gray-700 hover:text-gray-900 font-medium"
                  >
                    Upload
                  </Link>
                </div>
              </div>
              <UserButton />
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
      </div>
      {/* React Query Devtools - only visible in development */}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
