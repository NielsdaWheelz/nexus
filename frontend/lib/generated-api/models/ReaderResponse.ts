/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response for a reader (reading session).
 *
 * Returns a reader with typed ID format and full session state.
 *
 * Attributes:
 * id: Typed reader ID (format: rdr_<uuid>)
 * document_id: Typed document ID (format: doc_<uuid>)
 * current_position: Byte offset into canonical text
 * last_read_at: Timestamp of last read activity
 * created_at: UTC timestamp of reader creation
 * updated_at: UTC timestamp of last update
 */
export type ReaderResponse = {
  /**
   * Typed reader ID (rdr_<uuid>)
   */
  id: string;
  /**
   * Typed document ID (doc_<uuid>)
   */
  document_id: string;
  /**
   * Byte offset into canonical text
   */
  current_position?: number | null;
  /**
   * Timestamp of last read
   */
  last_read_at?: string | null;
  /**
   * UTC timestamp of creation
   */
  created_at: string;
  /**
   * UTC timestamp of last update
   */
  updated_at: string;
};
