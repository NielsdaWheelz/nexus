/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response item for a single annotation (used in list responses).
 *
 * All IDs are typed (e.g., ann_<uuid>, hl_<uuid>, chunk_<uuid>).
 *
 * Attributes:
 * id: Typed annotation ID (ann_<uuid>)
 * user_id: Typed user ID (usr_<uuid>)
 * document_id: Typed document ID (doc_<uuid>)
 * highlight_id: Optional typed highlight ID (hl_<uuid>)
 * chunk_id: Optional typed chunk ID (chunk_<uuid>)
 * content: The annotation text
 * created_at: UTC timestamp of creation
 * updated_at: UTC timestamp of last update
 */
export type AnnotationItem = {
  /**
   * Typed annotation ID (ann_<uuid>)
   */
  id: string;
  /**
   * Typed user ID (usr_<uuid>)
   */
  user_id: string;
  /**
   * Typed document ID (doc_<uuid>)
   */
  document_id: string;
  /**
   * Typed highlight ID (hl_<uuid>), if attached to highlight
   */
  highlight_id?: string | null;
  /**
   * Typed chunk ID (chunk_<uuid>), if attached to chunk
   */
  chunk_id?: string | null;
  /**
   * Annotation text content
   */
  content: string;
  /**
   * UTC timestamp of creation
   */
  created_at: string;
  /**
   * UTC timestamp of last update
   */
  updated_at: string;
};
