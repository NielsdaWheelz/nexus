"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { uploadDocument, isClientError, type ClientError } from "@/lib/api/documents";

type SourceKind = "pdf" | "epub" | "html";

type UploadStatus = "idle" | "uploading" | "success" | "error";

/**
 * Upload page for documents.
 *
 * Allows authenticated users to upload PDF, EPUB, or HTML files.
 * On success, redirects to the document detail page.
 */
export default function UploadPage() {
  const router = useRouter();

  const [file, setFile] = useState<File | null>(null);
  const [sourceKind, setSourceKind] = useState<SourceKind | "">("");
  const [title, setTitle] = useState("");
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const canSubmit = file !== null && sourceKind !== "" && status !== "uploading";

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] ?? null;
    setFile(selectedFile);
    // Clear any previous error when user selects a new file
    if (status === "error") {
      setStatus("idle");
      setErrorMessage(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!file || !sourceKind) {
      return;
    }

    setStatus("uploading");
    setErrorMessage(null);

    try {
      const result = await uploadDocument({
        file,
        sourceKind,
        title: title.trim() || undefined,
      });

      setStatus("success");
      // Redirect to the document detail page
      router.push(`/app/documents/${result.id}`);
    } catch (error) {
      setStatus("error");
      if (isClientError(error)) {
        setErrorMessage(error.message);
      } else {
        setErrorMessage("An unexpected error occurred");
      }
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 mb-6">Upload Document</h1>

      {/* Error banner */}
      {status === "error" && errorMessage && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
          <p className="text-red-700">{errorMessage}</p>
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-8 max-w-xl">
        <form onSubmit={handleSubmit}>
          {/* File input */}
          <div className="mb-6">
            <label htmlFor="file" className="block text-sm font-medium text-gray-700 mb-2">
              File
            </label>
            <input
              type="file"
              id="file"
              accept=".pdf,.epub,.html,.htm"
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
            {file && (
              <p className="mt-2 text-sm text-gray-500">Selected: {file.name}</p>
            )}
          </div>

          {/* Source kind selector */}
          <div className="mb-6">
            <label htmlFor="sourceKind" className="block text-sm font-medium text-gray-700 mb-2">
              Document Type
            </label>
            <select
              id="sourceKind"
              value={sourceKind}
              onChange={(e) => setSourceKind(e.target.value as SourceKind | "")}
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:ring-blue-500"
            >
              <option value="">Select type...</option>
              <option value="pdf">PDF</option>
              <option value="epub">EPUB</option>
              <option value="html">HTML</option>
            </select>
          </div>

          {/* Optional title */}
          <div className="mb-6">
            <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-2">
              Title <span className="text-gray-400">(optional)</span>
            </label>
            <input
              type="text"
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Defaults to filename"
              className="block w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:ring-blue-500"
            />
          </div>

          {/* Submit button */}
          <button
            type="submit"
            disabled={!canSubmit}
            className="w-full bg-blue-600 text-white px-4 py-2 rounded-md font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {status === "uploading" ? "Uploading…" : "Upload"}
          </button>
        </form>
      </div>
    </div>
  );
}

