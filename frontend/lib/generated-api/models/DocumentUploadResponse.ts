/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response for successful document upload.
 *
 * Returns a newly created document placeholder with typed ID format.
 *
 * Attributes:
 * id: Typed document ID (format: doc_<uuid>)
 * title: Document title (resolved from explicit override or filename)
 * source_kind: Type of source (pdf, epub, html)
 * created_at: UTC timestamp of upload
 * updated_at: UTC timestamp of creation
 */
export type DocumentUploadResponse = {
  /**
   * Typed document ID (doc_<uuid>)
   */
  id: string;
  /**
   * Document title
   */
  title: string;
  /**
   * Type of source document
   */
  source_kind: DocumentUploadResponse.source_kind;
  /**
   * UTC timestamp of upload
   */
  created_at: string;
  /**
   * UTC timestamp of creation
   */
  updated_at: string;
};
export namespace DocumentUploadResponse {
  /**
   * Type of source document
   */
  export enum source_kind {
    PDF = "pdf",
    EPUB = "epub",
    HTML = "html",
  }
}
