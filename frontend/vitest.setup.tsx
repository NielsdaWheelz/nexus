import "@testing-library/jest-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

/**
 * Create a test QueryClient with sensible defaults.
 * - No retries (fail fast in tests)
 * - No garbage collection caching (clean state between tests)
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
}

/**
 * Wrapper component that provides QueryClientProvider for tests.
 */
function createQueryWrapper() {
  const queryClient = createTestQueryClient();
  return function QueryWrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

/**
 * Render a component with QueryClientProvider for testing.
 *
 * @param ui - The React element to render
 * @param options - Optional render options
 * @returns The render result from @testing-library/react
 *
 * @example
 * ```tsx
 * import { renderWithQueryClient } from '@/vitest.setup';
 *
 * test('renders documents', async () => {
 *   renderWithQueryClient(<DocumentsPage />);
 *   await waitFor(() => {
 *     expect(screen.getByText('Documents')).toBeInTheDocument();
 *   });
 * });
 * ```
 */
export function renderWithQueryClient(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">
) {
  return render(ui, { wrapper: createQueryWrapper(), ...options });
}
