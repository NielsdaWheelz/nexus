"use client";

import { useState, useCallback, useEffect } from "react";
import {
  useAnnotations,
  useCreateAnnotation,
  useUpdateAnnotation,
  useDeleteAnnotation,
} from "@/lib/hooks/useAnnotations";
import type { AnnotationItem } from "@/lib/api/annotations";

/**
 * Props for the AnnotationsInspectorTab component.
 */
export interface AnnotationsInspectorTabProps {
  /** Currently selected highlight ID (null if none selected) */
  highlightId: string | null;
}

/**
 * Truncate text to a maximum length with ellipsis.
 */
function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 1) + "…";
}

/**
 * Format a date string for display (relative or absolute).
 */
function formatDate(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return "Today";
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * AnnotationsInspectorTab - Inspector panel content for the annotations tab.
 *
 * Features:
 * - Shows empty state when no highlight is selected
 * - Lists annotations for the selected highlight
 * - Create new annotation form
 * - Edit/delete existing annotations (inline)
 */
export function AnnotationsInspectorTab({
  highlightId,
}: AnnotationsInspectorTabProps) {
  // If no highlight is selected, show empty state
  if (!highlightId) {
    return (
      <div
        data-testid="annotations-inspector-no-highlight"
        className="text-sm text-gray-500 text-center py-8"
      >
        <p className="font-medium text-gray-700">No highlight selected</p>
        <p className="mt-1">
          Select a highlight in the document to view its annotations.
        </p>
      </div>
    );
  }

  return <AnnotationsPanelContent highlightId={highlightId} />;
}

/**
 * Inner component that handles the actual annotations display and CRUD.
 * Split out so we can conditionally call hooks only when highlightId is present.
 */
function AnnotationsPanelContent({ highlightId }: { highlightId: string }) {
  const { annotations, isLoading, isError, error } = useAnnotations(highlightId);
  const createMutation = useCreateAnnotation(highlightId);
  const updateMutation = useUpdateAnnotation(highlightId);
  const deleteMutation = useDeleteAnnotation(highlightId);

  // Create form state
  const [newContent, setNewContent] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit state - which annotation is being edited
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  // Reset all local state when highlight changes
  // This prevents stale edit state from persisting across highlight switches
  useEffect(() => {
    setNewContent("");
    setCreateError(null);
    setEditingId(null);
    setEditContent("");
    setEditError(null);
    createMutation.reset();
    updateMutation.reset();
    deleteMutation.reset();
  }, [highlightId]); // eslint-disable-line react-hooks/exhaustive-deps
  // Mutations are stable, but including them would cause infinite loop

  // Handle create annotation
  const handleCreate = useCallback(async () => {
    const trimmed = newContent.trim();
    if (!trimmed) return;

    setCreateError(null);
    try {
      await createMutation.createAnnotation(trimmed);
      setNewContent("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create annotation";
      setCreateError(message);
    }
  }, [newContent, createMutation]);

  // Handle start editing
  const handleStartEdit = useCallback((annotation: AnnotationItem) => {
    setEditingId(annotation.id);
    setEditContent(annotation.content);
    setEditError(null);
  }, []);

  // Handle cancel editing
  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    setEditContent("");
    setEditError(null);
  }, []);

  // Handle save edit
  const handleSaveEdit = useCallback(async () => {
    if (!editingId) return;
    const trimmed = editContent.trim();
    if (!trimmed) return;

    setEditError(null);
    try {
      await updateMutation.updateAnnotation({
        annotationId: editingId,
        content: trimmed,
      });
      setEditingId(null);
      setEditContent("");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update annotation";
      setEditError(message);
    }
  }, [editingId, editContent, updateMutation]);

  // Handle delete
  const handleDelete = useCallback(
    async (annotationId: string) => {
      if (!window.confirm("Delete this annotation?")) return;

      try {
        await deleteMutation.deleteAnnotation(annotationId);
      } catch (err) {
        // Error is handled by the mutation state
        console.error("Delete failed:", err);
      }
    },
    [deleteMutation]
  );

  // Loading state
  if (isLoading && annotations.length === 0) {
    return (
      <div
        data-testid="annotations-inspector-loading"
        className="text-sm text-gray-500 text-center py-8"
      >
        <div className="inline-block animate-spin rounded-full h-6 w-6 border-b-2 border-gray-400 mb-2"></div>
        <p>Loading annotations...</p>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div
        data-testid="annotations-inspector-error"
        className="text-sm text-red-600 bg-red-50 rounded-lg p-4"
      >
        <p className="font-medium">Failed to load annotations</p>
        <p className="text-red-500 mt-1">{error?.message ?? "Unknown error"}</p>
      </div>
    );
  }

  return (
    <div data-testid="annotations-inspector-content">
      {/* Create annotation form */}
      <div className="mb-4">
        <textarea
          data-testid="annotation-create-input"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Add a note..."
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          rows={3}
        />
        {createError && (
          <p
            data-testid="annotation-create-error"
            className="text-xs text-red-600 mt-1"
          >
            {createError}
          </p>
        )}
        <button
          data-testid="annotation-create-btn"
          onClick={handleCreate}
          disabled={!newContent.trim() || createMutation.isPending}
          className="mt-2 w-full px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {createMutation.isPending ? "Adding..." : "Add annotation"}
        </button>
      </div>

      {/* Annotations list */}
      {annotations.length === 0 ? (
        <div
          data-testid="annotations-inspector-empty"
          className="text-sm text-gray-500 text-center py-4"
        >
          <p>No annotations yet.</p>
          <p className="text-xs mt-1">Add a note using the form above.</p>
        </div>
      ) : (
        <div data-testid="annotations-inspector-list" className="space-y-3">
          <p className="text-xs text-gray-500">
            {annotations.length} annotation{annotations.length !== 1 ? "s" : ""}
          </p>

          {annotations.map((annotation) => (
            <AnnotationCard
              key={annotation.id}
              annotation={annotation}
              isEditing={editingId === annotation.id}
              editContent={editContent}
              editError={editError}
              isUpdating={updateMutation.isPending && editingId === annotation.id}
              isDeleting={deleteMutation.isPending}
              onEditContentChange={setEditContent}
              onStartEdit={() => handleStartEdit(annotation)}
              onCancelEdit={handleCancelEdit}
              onSaveEdit={handleSaveEdit}
              onDelete={() => handleDelete(annotation.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Props for AnnotationCard.
 */
interface AnnotationCardProps {
  annotation: AnnotationItem;
  isEditing: boolean;
  editContent: string;
  editError: string | null;
  isUpdating: boolean;
  isDeleting: boolean;
  onEditContentChange: (content: string) => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onDelete: () => void;
}

/**
 * Single annotation card with view/edit modes.
 */
function AnnotationCard({
  annotation,
  isEditing,
  editContent,
  editError,
  isUpdating,
  isDeleting,
  onEditContentChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
}: AnnotationCardProps) {
  if (isEditing) {
    return (
      <div
        data-testid={`annotation-card-${annotation.id}`}
        data-editing="true"
        className="p-3 bg-blue-50 border border-blue-200 rounded-lg"
      >
        <textarea
          data-testid="annotation-edit-input"
          value={editContent}
          onChange={(e) => onEditContentChange(e.target.value)}
          className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          rows={3}
          autoFocus
        />
        {editError && (
          <p
            data-testid="annotation-edit-error"
            className="text-xs text-red-600 mt-1"
          >
            {editError}
          </p>
        )}
        <div className="flex gap-2 mt-2">
          <button
            data-testid="annotation-save-btn"
            onClick={onSaveEdit}
            disabled={!editContent.trim() || isUpdating}
            className="px-3 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded disabled:opacity-50"
          >
            {isUpdating ? "Saving..." : "Save"}
          </button>
          <button
            data-testid="annotation-cancel-btn"
            onClick={onCancelEdit}
            disabled={isUpdating}
            className="px-3 py-1 text-xs text-gray-600 hover:text-gray-800"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid={`annotation-card-${annotation.id}`}
      data-editing="false"
      className="p-3 bg-white border border-gray-200 rounded-lg hover:border-gray-300 transition-colors"
    >
      <p className="text-sm text-gray-900 whitespace-pre-wrap">
        {annotation.content}
      </p>
      <div className="flex items-center justify-between mt-2">
        <p className="text-xs text-gray-500">
          {formatDate(annotation.updated_at)}
        </p>
        <div className="flex gap-2">
          <button
            data-testid="annotation-edit-btn"
            onClick={onStartEdit}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            Edit
          </button>
          <button
            data-testid="annotation-delete-btn"
            onClick={onDelete}
            disabled={isDeleting}
            className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

