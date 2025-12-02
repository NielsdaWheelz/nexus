"use client";

import { useUIStore, type InspectorTab } from "@/lib/state/ui";

/**
 * Props for the ReaderLayout component.
 */
export type ReaderLayoutProps = {
  /** The document ID being viewed. */
  documentId: string;
  /** Optional content for the center pane. */
  children?: React.ReactNode;
  /** Optional content for the highlights inspector tab. */
  highlightsContent?: React.ReactNode;
  /** Optional content for the annotations inspector tab. */
  annotationsContent?: React.ReactNode;
  /** Optional content for the chat inspector tab. */
  chatContent?: React.ReactNode;
  /** Optional content for the info inspector tab. */
  infoContent?: React.ReactNode;
};

/** Inspector tab configuration. */
const INSPECTOR_TABS: { id: InspectorTab; label: string }[] = [
  { id: "highlights", label: "Highlights" },
  { id: "annotations", label: "Annotations" },
  { id: "chat", label: "Chat" },
  { id: "info", label: "Info" },
];

/**
 * Three-pane reader layout.
 *
 * - Left: Navigation pane (library/document tree)
 * - Center: Reader content area
 * - Right: Inspector panel with tabs (collapsible)
 */
export function ReaderLayout({
  documentId,
  children,
  highlightsContent,
  annotationsContent,
  chatContent,
  infoContent,
}: ReaderLayoutProps) {
  const isInspectorOpen = useUIStore((s) => s.isInspectorOpen);
  const activeTab = useUIStore((s) => s.activeInspectorTab);
  const toggleInspector = useUIStore((s) => s.toggleInspector);
  const setInspectorOpen = useUIStore((s) => s.setInspectorOpen);
  const setActiveTab = useUIStore((s) => s.setActiveInspectorTab);

  return (
    <div className="flex h-[calc(100vh-4rem)] -mx-4 sm:-mx-6 lg:-mx-8 -my-8">
      {/* Left Pane: Navigation */}
      <aside className="w-64 flex-shrink-0 bg-gray-100 border-r border-gray-200 overflow-y-auto">
        <div className="p-4">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
            Library
          </h2>
          <nav className="space-y-1">
            <div className="px-3 py-2 text-sm text-gray-500 bg-gray-200 rounded">
              Document navigation
            </div>
            <div className="px-3 py-2 text-sm text-gray-400">
              (coming soon)
            </div>
          </nav>
        </div>
      </aside>

      {/* Center Pane: Reader */}
      <main className="flex-1 flex flex-col min-w-0 bg-white">
        {/* Top bar with inspector toggle */}
        <div className="flex items-center justify-end px-4 py-2 border-b border-gray-200 bg-gray-50">
          <button
            onClick={toggleInspector}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
            aria-label={isInspectorOpen ? "Close inspector" : "Open inspector"}
            data-testid="inspector-toggle"
          >
            {isInspectorOpen ? "Hide Inspector" : "Show Inspector"}
          </button>
        </div>

        {/* Content area */}
        <div className="flex-1 overflow-y-auto p-6">
          {children ?? (
            <div className="text-gray-400 text-center py-12">
              Reader content will appear here
            </div>
          )}
        </div>
      </main>

      {/* Right Pane: Inspector */}
      {isInspectorOpen && (
        <aside className="w-80 flex-shrink-0 bg-gray-50 border-l border-gray-200 flex flex-col">
          {/* Inspector header with tabs and close button */}
          <div className="flex items-center justify-between border-b border-gray-200 bg-white">
            <div className="flex" role="tablist">
              {INSPECTOR_TABS.map((tab) => (
                <button
                  key={tab.id}
                  role="tab"
                  aria-selected={activeTab === tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-3 py-3 text-sm font-medium transition-colors ${
                    activeTab === tab.id
                      ? "text-blue-600 border-b-2 border-blue-600"
                      : "text-gray-600 hover:text-gray-900"
                  }`}
                  data-testid={`tab-${tab.id}`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <button
              onClick={() => setInspectorOpen(false)}
              className="p-2 mr-1 text-gray-500 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
              aria-label="Close inspector"
              data-testid="inspector-close"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          {/* Inspector body */}
          <div className="flex-1 overflow-y-auto p-4">
            <InspectorContent
              tab={activeTab}
              highlightsContent={highlightsContent}
              annotationsContent={annotationsContent}
              chatContent={chatContent}
              infoContent={infoContent}
            />
          </div>
        </aside>
      )}
    </div>
  );
}

/**
 * Props for InspectorContent.
 */
interface InspectorContentProps {
  tab: InspectorTab;
  highlightsContent?: React.ReactNode;
  annotationsContent?: React.ReactNode;
  chatContent?: React.ReactNode;
  infoContent?: React.ReactNode;
}

/**
 * Stub content for each inspector tab, with optional custom content.
 */
function InspectorContent({
  tab,
  highlightsContent,
  annotationsContent,
  chatContent,
  infoContent,
}: InspectorContentProps) {
  // Use custom content if provided
  const customContent: Record<InspectorTab, React.ReactNode | undefined> = {
    highlights: highlightsContent,
    annotations: annotationsContent,
    chat: chatContent,
    info: infoContent,
  };

  if (customContent[tab]) {
    return (
      <div data-testid={`inspector-content-${tab}`}>
        {customContent[tab]}
      </div>
    );
  }

  // Fall back to stub content
  const stubContent: Record<InspectorTab, { title: string; description: string }> = {
    highlights: {
      title: "Highlights",
      description: "Your document highlights will appear here.",
    },
    annotations: {
      title: "Annotations",
      description: "Your annotations will appear here.",
    },
    chat: {
      title: "Chat",
      description: "Chat with your document here.",
    },
    info: {
      title: "Document Info",
      description: "Document metadata and details.",
    },
  };

  const { title, description } = stubContent[tab];

  return (
    <div data-testid={`inspector-content-${tab}`}>
      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2">
        {title}
      </h3>
      <p className="text-sm text-gray-500">{description}</p>
      <div className="mt-4 text-xs text-gray-400">(coming soon)</div>
    </div>
  );
}

