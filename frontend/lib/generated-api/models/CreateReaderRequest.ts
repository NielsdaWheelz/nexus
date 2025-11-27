/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API request for creating a reader.
 *
 * Accepts a document_id and creates a reading session for the authenticated user.
 * GET-or-create semantics: returns existing reader if already created.
 *
 * Attributes:
 * document_id: Typed document ID (format: doc_<uuid>)
 */
export type CreateReaderRequest = {
  /**
   * Typed document ID (doc_<uuid>)
   */
  document_id: string;
};
